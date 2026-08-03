import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AgentTrace, TraceStep } from '../../../core/api/api.types';

/**
 * What the agent did to produce the answer above it.
 *
 * WHY THIS PANEL EXISTS. From outside, every RAG system looks identical: a question goes
 * in, prose comes out. This shows the parts that differ — the query the model WROTE
 * (rarely the one the user typed), the scores it ranked on, whether the reflection
 * checkpoint caught an undefined legal term and went back for a definition, and how much
 * of the iteration budget it spent.
 *
 * Presentational only: it takes a trace and renders it. No injection, no HTTP, no state.
 */
@Component({
  selector: 'app-agent-trace',
  imports: [DecimalPipe, MatIconModule, MatTooltipModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './agent-trace.html',
  styleUrl: './agent-trace.scss',
})
export class AgentTracePanel {
  readonly trace = input.required<AgentTrace>();
  /** The user's original question, shown against the agent's reformulated query. */
  readonly question = input<string>('');
  /**
   * True once the run has finished (its `final` or `error` event arrived) — see
   * chat-page.ts's `streaming` flag. While a run is still in flight with zero steps so far,
   * the panel stays hidden rather than flashing an empty box that might fill in a moment
   * later. Once it's settled, a genuinely empty trace becomes visible instead of silently
   * rendering nothing — which is exactly how "the agent never even searched the corpus"
   * used to be indistinguishable from "the trace panel doesn't work at all".
   */
  readonly settled = input<boolean>(true);

  protected readonly expanded = computed(
    () => this.trace().steps.length > 0 || this.settled(),
  );

  protected icon(kind: TraceStep['kind']): string {
    return { retrieval: 'search', reflection: 'psychology', answer: 'auto_fix_high' }[kind];
  }

  /** Ratio for the score bar. Cosine similarity is already 0..1; clamp defensively. */
  protected barWidth(score: number): number {
    return Math.max(0, Math.min(1, score)) * 100;
  }
}
