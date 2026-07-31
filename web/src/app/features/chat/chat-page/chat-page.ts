import { BreakpointObserver } from '@angular/cdk/layout';
import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';
import { map } from 'rxjs';
import { Citation, ConversationSummary, MessageRole } from '../../../core/api/api.types';
import { ChatApi } from '../../../core/api/chat.api';
import { MarkdownPipe } from '../../../core/markdown/markdown.pipe';
import { CitationCard } from '../citation-card/citation-card';
import { ConversationList } from '../conversation-list/conversation-list';
import { MessageComposer } from '../message-composer/message-composer';

interface ChatMessage {
  /**
   * A stable identity for `@for ... track`. Tracking by $index makes Angular tear down and
   * rebuild every message node whenever the array changes, which collapses open citation
   * panels and loses scroll position mid-conversation.
   */
  id: string;
  role: MessageRole;
  content: string;
  citations: Citation[];
  latencyMs: number | null;
  createdAt: Date;
  /** The send failed and the server stored nothing — see the comment in `send()`. */
  failed: boolean;
}

/** Shown on an empty conversation. Real questions the corpus can actually answer. */
const SUGGESTIONS = [
  'Quelle est la peine pour vol simple ?',
  'Que dit la Constitution sur la liberté d’expression ?',
  'Quelles sont les circonstances aggravantes du vol ?',
];

@Component({
  selector: 'app-chat-page',
  imports: [
    MatSidenavModule,
    MatProgressBarModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    DatePipe,
    MarkdownPipe,
    CitationCard,
    ConversationList,
    MessageComposer,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './chat-page.html',
  styleUrl: './chat-page.scss',
})
export class ChatPage {
  private readonly chatApi = inject(ChatApi);
  private readonly router = inject(Router);
  private readonly breakpoints = inject(BreakpointObserver);

  /** Bound from the `:conversationId` route param; undefined on a bare /chat. */
  readonly conversationId = input<string | undefined>(undefined);

  protected readonly suggestions = SUGGESTIONS;
  protected readonly conversations = signal<ConversationSummary[]>([]);
  protected readonly messages = signal<ChatMessage[]>([]);
  protected readonly pending = signal(false);
  protected readonly loadingHistory = signal(false);
  protected readonly copiedId = signal<string | null>(null);

  /**
   * Below this width the sidenav switches from `side` (permanently docked, squeezing the
   * chat) to `over` (a drawer above it). At 380px of drawer on a 390px phone, `side` leaves
   * no room to read an answer at all.
   */
  protected readonly isHandset = toSignal(
    this.breakpoints.observe('(max-width: 900px)').pipe(map((state) => state.matches)),
    { initialValue: false },
  );

  protected readonly drawerOpen = signal(true);

  private readonly log = viewChild<ElementRef<HTMLElement>>('log');
  private readonly loadedId = signal<string | null>(null);

  constructor() {
    this.reloadConversations();

    effect(() => {
      const id = this.conversationId() ?? null;

      // untracked: re-run when the ROUTE changes, never because of this effect's own
      // writes. Reading loadedId/messages as dependencies would make it self-triggering.
      untracked(() => {
        if (id === this.loadedId()) {
          return;
        }
        this.loadedId.set(id);

        if (id === null) {
          this.messages.set([]);
          return;
        }
        this.loadHistory(id);
      });
    });

    // Follow the conversation as it grows.
    effect(() => {
      this.messages();
      this.pending();

      // setTimeout, not a direct call: this effect runs during change detection, before
      // Angular has written the new message to the DOM. Scrolling now would target the
      // PREVIOUS scrollHeight and stop one message short, every time.
      setTimeout(() => {
        const element = this.log()?.nativeElement;
        element?.scrollTo({ top: element.scrollHeight, behavior: 'smooth' });
      });
    });

    // On a phone the drawer starts closed; the answer matters more than the history list.
    effect(() => this.drawerOpen.set(!this.isHandset()));
  }

  protected send(question: string): void {
    if (this.pending()) {
      return;
    }
    this.pending.set(true);
    this.messages.update((current) => [...current, message('user', question)]);

    if (this.isHandset()) {
      this.drawerOpen.set(false);
    }

    this.chatApi.ask(question, this.conversationId() ?? null).subscribe({
      next: (response) => {
        this.messages.update((current) => [
          ...current,
          { ...message('assistant', response.answer), citations: response.citations },
        ]);
        this.pending.set(false);

        if (this.conversationId() === undefined) {
          // Claim the new id BEFORE navigating. The route effect would otherwise see an id
          // it has not loaded, fetch the history, and overwrite `messages` — and the
          // history endpoint returns no citations, so the ones just received would vanish
          // the instant the URL updated.
          this.loadedId.set(response.conversation_id);
          void this.router.navigate(['/chat', response.conversation_id]);
        }
        this.reloadConversations();
      },
      error: () => {
        this.pending.set(false);

        // The server persists the question and the answer together, AFTER the agent
        // succeeds (app/services/chat_service.py). A failure means nothing was stored, so
        // this bubble is marked failed rather than left looking sent — otherwise it would
        // mysteriously vanish on the next reload.
        this.messages.update((current) =>
          current.map((entry, index) =>
            index === current.length - 1 ? { ...entry, failed: true } : entry,
          ),
        );
      },
    });
  }

  protected retry(id: string): void {
    const failed = this.messages().find((entry) => entry.id === id);
    if (!failed) {
      return;
    }
    this.messages.update((current) => current.filter((entry) => entry.id !== id));
    this.send(failed.content);
  }

  protected async copy(entry: ChatMessage): Promise<void> {
    try {
      await navigator.clipboard.writeText(entry.content);
      this.copiedId.set(entry.id);
      setTimeout(() => this.copiedId.set(null), 2000);
    } catch {
      // Clipboard access can be denied (insecure origin, permissions policy). Silently
      // leaving the button un-ticked is better than an error toast for a convenience action.
    }
  }

  protected toggleDrawer(): void {
    this.drawerOpen.update((open) => !open);
  }

  private loadHistory(id: string): void {
    this.loadingHistory.set(true);

    this.chatApi.history(id).subscribe({
      next: (history) => {
        this.messages.set(
          history.map((entry) => ({
            id: crypto.randomUUID(),
            role: entry.role,
            content: entry.content,
            // GET /api/conversations/{id} returns role/content/latency_ms/created_at only.
            // The citations ARE persisted (a `citations` table keyed to the message) but no
            // endpoint exposes them, so replayed history shows answers without their
            // sources. Fixing that is a backend change, not something to fake here.
            citations: [],
            latencyMs: entry.latency_ms,
            createdAt: new Date(entry.created_at),
            failed: false,
          })),
        );
        this.loadingHistory.set(false);
      },
      error: () => {
        this.loadingHistory.set(false);
        this.messages.set([]);
        void this.router.navigate(['/chat']);
      },
    });
  }

  private reloadConversations(): void {
    this.chatApi.listConversations().subscribe({
      next: (conversations) => this.conversations.set(conversations),
      error: () => {
        // Non-fatal: the sidebar keeps its previous contents and the snackbar has explained.
      },
    });
  }
}

function message(role: MessageRole, content: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    citations: [],
    latencyMs: null,
    createdAt: new Date(),
    failed: false,
  };
}
