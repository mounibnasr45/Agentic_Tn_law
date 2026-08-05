import { DatePipe, DecimalPipe, PercentPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription, timer } from 'rxjs';
import { AdminApi } from '../../../core/api/admin.api';
import { AdminDocument, AdminUser, CorpusStatus } from '../../../core/api/api.types';
import { AuthStore } from '../../../core/auth/auth.store';
import { I18nService } from '../../../core/i18n/i18n.service';

/** How often to re-read corpus status while an ingest is in flight. */
const POLL_INTERVAL_MS = 1000;

/**
 * Corpus administration: drop a PDF, watch it become searchable chunks.
 *
 * WHY POLLING AND NOT SSE/WEBSOCKET. Progress lives in two integers on the document row,
 * so "what is the state?" is already a cheap SELECT. A streaming transport would add a
 * long-lived connection that free-tier proxies drop on idle, needs its own reconnect
 * logic, and would still be reading the same two columns. A 1s poll that stops the moment
 * nothing is ingesting costs less complexity and survives a dyno restart mid-upload —
 * the poll simply picks the state back up.
 */
@Component({
  selector: 'app-admin-page',
  imports: [
    DatePipe,
    DecimalPipe,
    PercentPipe,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressBarModule,
    MatTableModule,
    MatTooltipModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './admin-page.html',
  styleUrl: './admin-page.scss',
})
export class AdminPage {
  protected readonly t = inject(I18nService);

  private readonly api = inject(AdminApi);
  private readonly destroyRef = inject(DestroyRef);
  private readonly authStore = inject(AuthStore);

  protected readonly corpus = signal<CorpusStatus | null>(null);
  protected readonly loadFailed = signal(false);

  /** Set while bytes are on the wire. Distinct from indexing progress — see AdminApi. */
  protected readonly uploadPercent = signal<number | null>(null);
  protected readonly uploadError = signal<string | null>(null);
  /** Shown when a re-upload was recognised as already indexed and skipped. */
  protected readonly skippedNotice = signal<string | null>(null);

  protected readonly isDragging = signal(false);

  protected readonly columns = ['title', 'status', 'progress', 'chunks', 'indexed'] as const;
  protected readonly userColumns = [
    'email',
    'role',
    'messages',
    'sessions',
    'actions',
  ] as const;

  protected readonly documents = computed(() => this.corpus()?.documents ?? []);
  protected readonly isBusy = computed(
    () => this.uploadPercent() !== null || (this.corpus()?.is_ingesting ?? false),
  );

  private poll: Subscription | null = null;

  // --- users ------------------------------------------------------------------------

  protected readonly users = signal<AdminUser[]>([]);
  protected readonly usersLoadFailed = signal(false);
  /** The row currently mid-request, so only ITS button shows a pending state — not every
   * row's, which would make an admin wonder whether they clicked the right one. */
  protected readonly pendingUserId = signal<string | null>(null);

  constructor() {
    this.refresh();
    this.loadUsers();
  }

  private loadUsers(): void {
    this.api
      .users()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (users) => {
          this.users.set(users);
          this.usersLoadFailed.set(false);
        },
        error: () => this.usersLoadFailed.set(true),
      });
  }

  protected isSelf(user: AdminUser): boolean {
    return this.authStore.user()?.id === user.id;
  }

  protected toggleAdmin(user: AdminUser): void {
    this.pendingUserId.set(user.id);

    this.api
      .setAdmin(user.id, !user.is_admin)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        // The server's own detail ("Vous ne pouvez pas retirer vos propres droits
        // administrateur.") already reaches the user via httpErrorInterceptor on error,
        // so error handling here is only clearing the pending state — the button, not a
        // second message.
        next: (updated) => {
          this.users.update((current) =>
            current.map((u) => (u.id === updated.id ? updated : u)),
          );
          this.pendingUserId.set(null);
        },
        error: () => this.pendingUserId.set(null),
      });
  }

  // --- upload ---------------------------------------------------------------------

  protected onDragOver(event: DragEvent): void {
    // Without BOTH preventDefault and a dragover handler, the browser's default action
    // takes over and navigates away to the dropped file — losing the whole SPA.
    event.preventDefault();
    this.isDragging.set(true);
  }

  protected onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(false);
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(false);

    const file = event.dataTransfer?.files?.[0];
    if (file) {
      this.send(file);
    }
  }

  protected onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.send(file);
    }
    // Clear it, or picking the SAME file twice in a row fires no change event and the
    // second upload silently never happens.
    input.value = '';
  }

  private send(file: File): void {
    this.uploadError.set(null);
    this.skippedNotice.set(null);
    this.uploadPercent.set(0);

    this.api
      .upload(file)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (event) => {
          if (event.kind === 'sending') {
            this.uploadPercent.set(event.percent);
            return;
          }

          this.uploadPercent.set(null);

          if (!event.body.processing) {
            this.skippedNotice.set(
              `« ${event.body.document.title} » est déjà indexé avec l'encodeur actuel — rien à refaire.`,
            );
          }

          // The 202 means "queued", not "done". Start polling for the indexing progress
          // that begins after the response.
          this.refresh();
        },
        error: (error: { status?: number; error?: { detail?: string } }) => {
          this.uploadPercent.set(null);
          this.uploadError.set(
            error.error?.detail ??
              (error.status === 403
                ? "Accès réservé aux administrateurs."
                : "Échec de l'envoi. Réessayez."),
          );
        },
      });
  }

  // --- polling --------------------------------------------------------------------

  protected refresh(): void {
    this.api
      .corpus()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (corpus) => {
          this.corpus.set(corpus);
          this.loadFailed.set(false);
          if (corpus.is_ingesting) {
            this.startPolling();
          } else {
            this.stopPolling();
          }
        },
        error: () => {
          this.loadFailed.set(true);
          // Stop on error rather than hammering a failing endpoint every second.
          this.stopPolling();
        },
      });
  }

  private startPolling(): void {
    if (this.poll) {
      return; // already running; a second timer would double the request rate
    }

    this.poll = timer(POLL_INTERVAL_MS, POLL_INTERVAL_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.api
          .corpus()
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            next: (corpus) => {
              this.corpus.set(corpus);
              if (!corpus.is_ingesting) {
                this.stopPolling();
              }
            },
            error: () => this.stopPolling(),
          });
      });
  }

  private stopPolling(): void {
    this.poll?.unsubscribe();
    this.poll = null;
  }

  // --- view helpers ---------------------------------------------------------------

  protected statusLabel(status: AdminDocument['status']): string {
    return (
      { pending: 'En attente', processing: 'Indexation', indexed: 'Indexé', failed: 'Échec' }[
        status
      ] ?? status
    );
  }

  protected statusIcon(status: AdminDocument['status']): string {
    return (
      { pending: 'schedule', processing: 'sync', indexed: 'check_circle', failed: 'error' }[
        status
      ] ?? 'help'
    );
  }
}
