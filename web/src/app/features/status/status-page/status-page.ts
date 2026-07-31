import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { HealthResponse } from '../../../core/api/api.types';
import { HealthApi } from '../../../core/api/health.api';

/**
 * What /api/health reports.
 *
 * Unauthenticated on purpose. "Is the service up, and is the corpus actually indexed?" is
 * a question you most want answered when you cannot log in — putting it behind the login
 * wall would make it useless in exactly the situation it exists for.
 */
@Component({
  selector: 'app-status-page',
  imports: [MatCardModule, MatIconModule, MatButtonModule, MatProgressBarModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './status-page.html',
  styleUrl: './status-page.scss',
})
export class StatusPage {
  private readonly healthApi = inject(HealthApi);

  protected readonly health = signal<HealthResponse | null>(null);
  protected readonly pending = signal(false);
  protected readonly unreachable = signal(false);

  constructor() {
    this.refresh();
  }

  protected refresh(): void {
    this.pending.set(true);

    this.healthApi.health().subscribe({
      next: (health) => {
        this.health.set(health);
        this.unreachable.set(false);
        this.pending.set(false);
      },
      error: () => {
        // Distinct from "degraded": we got no answer at all, so we cannot claim anything
        // about the database or the corpus.
        this.health.set(null);
        this.unreachable.set(true);
        this.pending.set(false);
      },
    });
  }
}
