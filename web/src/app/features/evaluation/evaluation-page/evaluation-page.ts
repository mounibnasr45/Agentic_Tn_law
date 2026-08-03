import { DecimalPipe, PercentPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AblationArm, EvaluationResponse } from '../../../core/api/api.types';
import { EvaluationApi } from '../../../core/api/evaluation.api';

/**
 * The retrieval evaluation, published.
 *
 * WHY THIS PAGE EXISTS. Everything else in the app shows what the system DOES. This shows
 * how well it does it, and — more importantly — what the measurement changed. Two results
 * carry the page:
 *
 *   1. The encoder was silently truncating 38% of the corpus. Nothing failed; only the
 *      metrics revealed it. hit@5 0.500 -> 0.839.
 *   2. Dense-only beat every hybrid configuration, so dense-only is what ships — even
 *      though "hybrid" is the better-sounding word.
 *
 * The numbers are read from eval/baseline.json, the same artefact CI gates against, so the
 * page cannot drift from the measurement.
 */
@Component({
  selector: 'app-evaluation-page',
  imports: [
    DecimalPipe,
    PercentPipe,
    MatCardModule,
    MatIconModule,
    MatTableModule,
    MatTooltipModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './evaluation-page.html',
  styleUrl: './evaluation-page.scss',
})
export class EvaluationPage {
  private readonly api = inject(EvaluationApi);

  protected readonly data = signal<EvaluationResponse | null>(null);
  protected readonly failed = signal(false);

  protected readonly columns = [
    'name',
    'arm',
    'hit1',
    'hit3',
    'hit5',
    'hit10',
    'mrr',
    'ndcg',
  ] as const;

  /** Sorted best-first on hit@5 — the metric the CI gate actually enforces. */
  protected readonly arms = computed(() =>
    [...(this.data()?.arms ?? [])].sort((a, b) => b.hit_at_5 - a.hit_at_5),
  );

  protected readonly best = computed(() => this.arms()[0] ?? null);

  /** Absolute gain in hit@5 from the encoder fix, in points. */
  protected readonly encoderGain = computed(() => {
    const fix = this.data()?.encoder_fix;
    return fix ? fix.after_hit_at_5 - fix.before_hit_at_5 : 0;
  });

  constructor() {
    this.api.results().subscribe({
      next: (data) => {
        this.data.set(data);
        this.failed.set(false);
      },
      error: () => this.failed.set(true),
    });
  }

  protected isBest(arm: AblationArm): boolean {
    return arm.name === this.best()?.name;
  }

  /**
   * True when this arm is the one actually deployed.
   *
   * weight 0.0 == dense-only, and settings.hybrid_weight_bm25 is 0.0 — so the deployed
   * configuration and the winning configuration are the same row. Marking both is the
   * point: it shows the measurement was acted on rather than filed away.
   */
  protected isDeployed(arm: AblationArm): boolean {
    const w = this.data()?.deployed_weight_bm25;
    if (w === undefined) {
      return false;
    }
    return arm.name === `weighted w=${w.toFixed(1)}`;
  }
}
