import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { MatExpansionModule } from '@angular/material/expansion';
import { Citation } from '../../../core/api/api.types';
import { I18nService } from '../../../core/i18n/i18n.service';

/**
 * One citation, collapsed to its article number and expandable to the source excerpt.
 *
 * Every field shown here is backed by a real `chunks` row. Bug 4 in this project's history
 * was that `sources` was a hardcoded placeholder string — this component only renders what
 * the retriever actually returned, including the score and rank that prove it.
 */
@Component({
  selector: 'app-citation-card',
  imports: [MatExpansionModule, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-expansion-panel class="citation">
      <mat-expansion-panel-header>
        <mat-panel-title>
          <!-- article_number is null for text outside a numbered article, e.g. the preamble. -->
          📖 {{ citation().article_number ?? this.t.s().preamble }}
        </mat-panel-title>
        <mat-panel-description>
          {{ citation().source }} · score {{ citation().score | number: '1.3-3' }} · rang
          {{ citation().rank }}
        </mat-panel-description>
      </mat-expansion-panel-header>

      <p class="citation-excerpt">{{ citation().excerpt }}</p>
    </mat-expansion-panel>
  `,
  styles: `
    .citation-excerpt {
      margin: 0;
      white-space: pre-wrap;
      font: var(--mat-sys-body-medium);
    }
  `,
})
export class CitationCard {
  protected readonly t = inject(I18nService);

  readonly citation = input.required<Citation>();
}
