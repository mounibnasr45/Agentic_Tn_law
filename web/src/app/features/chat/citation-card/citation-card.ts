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
    <!-- collapsedHeight/expandedHeight "auto", not the Material default fixed 48px: a
         long filename plus score and rank wraps to two lines on a narrow screen, and a
         fixed-height header clips wrapped content instead of growing for it — the
         overflow then bleeds visually into whatever renders next, which is what made
         cards overlap on mobile. -->
      <mat-expansion-panel class="citation">
      <mat-expansion-panel-header collapsedHeight="auto" expandedHeight="auto">
        <!-- ONE projected element, not Material's title+description pair: those two lay
             out side by side in a row Material owns internally, which is what wrapped
             into an overlap in the first place. A single title containing both lines,
             stacked by CSS this component actually controls, sidesteps that layout
             entirely rather than fighting it. -->
        <mat-panel-title class="citation-title">
          <span class="citation-article">
            <!-- article_number is null for text outside a numbered article, e.g. the preamble. -->
            📖 {{ citation().article_number ?? this.t.s().preamble }}
          </span>
          <span class="citation-meta">
            {{ citation().source }} · score {{ citation().score | number: '1.3-3' }} · rang
            {{ citation().rank }}
          </span>
        </mat-panel-title>
      </mat-expansion-panel-header>

      <p class="citation-excerpt">{{ citation().excerpt }}</p>
    </mat-expansion-panel>
  `,
  styles: `
    .citation-title {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 0.15rem;
      // Material's own .mat-expansion-panel-header-title sets overflow:hidden and a
      // single-line white-space by default, which is exactly what needs to NOT apply
      // here — this component owns wrapping now, not Material's row layout.
      overflow: visible;
      white-space: normal;
    }

    .citation-meta {
      font: var(--mat-sys-body-small);
      opacity: 0.7;
      overflow-wrap: anywhere;
    }

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
