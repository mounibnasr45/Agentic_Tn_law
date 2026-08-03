import { BreakpointObserver } from '@angular/cdk/layout';
import { DatePipe, Location } from '@angular/common';
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
import {
  AgentTrace,
  ChatStreamEvent,
  Citation,
  ConversationSummary,
  MessageRole,
} from '../../../core/api/api.types';
import { ChatApi } from '../../../core/api/chat.api';
import { MarkdownPipe } from '../../../core/markdown/markdown.pipe';
import { CitationCard } from '../citation-card/citation-card';
import { ConversationList } from '../conversation-list/conversation-list';
import { AgentTracePanel } from '../agent-trace/agent-trace';
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
  /**
   * What the agent did for THIS answer. Live-only: /conversations/{id} replays messages
   * without traces, because a stored trace would describe a corpus version that may no
   * longer exist. Null on user messages and on replayed history.
   *
   * For an assistant message still being answered, this starts as an EMPTY trace (not
   * null) the moment the bubble is created, so `step` events have somewhere to land as
   * they arrive — see applyStreamEvent().
   */
  trace: AgentTrace | null;
  /** The question that produced this answer, shown against the agent's own query. */
  question: string;
  latencyMs: number | null;
  createdAt: Date;
  /** The send failed and the server stored nothing — see the comment in `send()`. */
  failed: boolean;
  /**
   * True from the moment an assistant bubble is created until its `final` (or `error`)
   * event arrives. Drives the in-bubble "consulte les textes…" placeholder — distinct from
   * the page-level `pending` signal, which just disables the composer.
   */
  streaming: boolean;
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
    AgentTracePanel,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './chat-page.html',
  styleUrl: './chat-page.scss',
})
export class ChatPage {
  private readonly chatApi = inject(ChatApi);
  private readonly router = inject(Router);
  private readonly location = inject(Location);
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
        if (!element) {
          return;
        }

        // The typeof check is not defensive noise. This runs inside a setTimeout, so it
        // fires OUTSIDE Angular's error handling — in jsdom, where Element.scrollTo is not
        // implemented, it throws an uncaught TypeError that the test runner reports as a
        // top-level error rather than a failure. Nine of them per run, attributed to
        // whichever test happened to be in flight, drowning any real signal.
        if (typeof element.scrollTo === 'function') {
          element.scrollTo({ top: element.scrollHeight, behavior: 'smooth' });
        } else {
          // jsdom and older browsers: assigning scrollTop is the universally supported
          // fallback, and it lands in the same place without the smooth animation.
          element.scrollTop = element.scrollHeight;
        }
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

    const assistantId = crypto.randomUUID();
    this.messages.update((current) => [
      ...current,
      message('user', question),
      {
        ...message('assistant', ''),
        id: assistantId,
        // Non-null from the start, so a `step` event arriving before the composer even
        // finishes disabling has somewhere to land.
        trace: { steps: [], iterations_used: 0, max_iterations: 0, regrounded: false },
        question,
        streaming: true,
      },
    ]);

    if (this.isHandset()) {
      this.drawerOpen.set(false);
    }

    this.chatApi.askStream(question, this.conversationId() ?? null).subscribe({
      next: (event) => this.applyStreamEvent(assistantId, event),
      error: () => this.failSend(assistantId),
      // No `complete` handler: the 'final' branch of applyStreamEvent() already does
      // everything completion would — the stream simply ends after it.
    });
  }

  /** One line of the NDJSON stream — see ChatApi.askStream and app/api/routes/chat.py. */
  private applyStreamEvent(assistantId: string, event: ChatStreamEvent): void {
    switch (event.event) {
      case 'step':
        this.messages.update((current) =>
          current.map((entry) =>
            entry.id === assistantId && entry.trace
              ? { ...entry, trace: { ...entry.trace, steps: [...entry.trace.steps, event.data] } }
              : entry,
          ),
        );
        return;

      case 'final':
        this.messages.update((current) =>
          current.map((entry) =>
            entry.id === assistantId
              ? {
                  ...entry,
                  content: event.data.answer,
                  citations: event.data.citations,
                  trace: event.data.trace,
                  streaming: false,
                }
              : entry,
          ),
        );
        this.pending.set(false);

        if (this.conversationId() === undefined) {
          // replaceState, NOT router.navigate — and this is the whole reason citations and
          // traces used to vanish the instant a NEW conversation got its id.
          //
          // app.routes.ts declares 'chat' and 'chat/:conversationId' as TWO routes bound to
          // this same component. Navigating between them is a route CHANGE, so Angular
          // destroys this component and builds a fresh one. `loadedId` is a field on the
          // instance, so the guard it exists to provide dies with it: the new component
          // sees an id it has never loaded, refetches history, and history carries neither
          // citations nor a trace. The answer's sources disappeared a frame after arriving.
          //
          // Location.replaceState rewrites the URL without routing, so the component (and
          // everything in `messages`) survives. Deep-linking still works: a cold load of
          // /chat/{id} matches the second route and legitimately loads history.
          this.loadedId.set(event.data.conversation_id);
          this.location.replaceState(`/chat/${event.data.conversation_id}`);
        }
        this.reloadConversations();
        return;

      case 'error':
        this.failSend(assistantId);
    }
  }

  /**
   * The server persists the question and the answer together, AFTER the agent succeeds
   * (app/services/chat_service.py). A failure — network, or an in-band `error` event — means
   * nothing was stored, so the placeholder assistant bubble is dropped entirely and the
   * user's OWN question is marked failed instead of left looking sent. `retry()` reads
   * `.content` off whatever is marked failed, which only holds the original question text
   * on the user bubble — the assistant placeholder's content is still empty at this point.
   */
  private failSend(assistantId: string): void {
    this.pending.set(false);
    this.messages.update((current) => {
      const withoutPlaceholder = current.filter((entry) => entry.id !== assistantId);
      return withoutPlaceholder.map((entry, index) =>
        index === withoutPlaceholder.length - 1 ? { ...entry, failed: true } : entry,
      );
    });
  }

  /**
   * A reground answer can accumulate citations from several retrieval calls (initial search
   * plus reflection follow-ups), so `entry.citations` can run into the dozens. The panel only
   * ever shows the best 5 — sorted by score, not retrieval order, since later reflection
   * searches are not necessarily less relevant than the first one.
   */
  protected topCitations(entry: ChatMessage): Citation[] {
    return [...entry.citations].sort((a, b) => b.score - a.score).slice(0, 5);
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
            // Same reason as citations: a trace describes one live run against one
            // corpus version, so replaying a stored one beside old text would be a
            // claim we cannot stand behind. History shows the answer, not the path.
            trace: null,
            question: '',
            latencyMs: entry.latency_ms,
            createdAt: new Date(entry.created_at),
            failed: false,
            streaming: false,
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
    trace: null,
    question: '',
    latencyMs: null,
    createdAt: new Date(),
    failed: false,
    streaming: false,
  };
}
