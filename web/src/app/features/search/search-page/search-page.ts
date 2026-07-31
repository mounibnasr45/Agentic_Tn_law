import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSliderModule } from '@angular/material/slider';
import { FusionStrategy, SearchResponse } from '../../../core/api/api.types';
import { SearchApi } from '../../../core/api/search.api';
import { CitationCard } from '../../chat/citation-card/citation-card';

/**
 * Retrieval with no LLM.
 *
 * This page exists because the retrieval quality IS the project — the eval harness moved
 * hit@5 from 0.500 to 0.839 by finding an encoder that was silently truncating chunks. An
 * answer from the agent hides all of that behind fluent prose; this shows the ranked chunks
 * exactly as the retriever returned them, and lets you move the fusion knobs yourself.
 */
@Component({
  selector: 'app-search-page',
  imports: [
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSliderModule,
    MatCheckboxModule,
    MatButtonModule,
    MatProgressBarModule,
    CitationCard,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './search-page.html',
  styleUrl: './search-page.scss',
})
export class SearchPage {
  private readonly fb = inject(FormBuilder);
  private readonly searchApi = inject(SearchApi);

  protected readonly pending = signal(false);
  protected readonly response = signal<SearchResponse | null>(null);

  protected readonly fusionStrategies: { value: FusionStrategy; label: string }[] = [
    { value: 'weighted', label: 'Pondérée (min-max sur les deux arms)' },
    { value: 'rrf', label: 'RRF (fusion par rang)' },
  ];

  protected readonly form = this.fb.nonNullable.group({
    query: ['', [Validators.required, Validators.minLength(3)]],
    topK: [5, [Validators.required, Validators.min(1), Validators.max(50)]],
    fusion: ['weighted' as FusionStrategy, Validators.required],
    /**
     * When checked we omit weight_bm25 entirely and the server applies its configured
     * HYBRID_WEIGHT_BM25 — which is 0.0, dense-only, because that measured BEST on this
     * corpus. Every weighted hybrid scored worse. Overriding here is how you check that.
     */
    useServerWeight: [true],
    weightBm25: [0],
  });

  protected submit(): void {
    if (this.form.invalid || this.pending()) {
      return;
    }
    this.pending.set(true);

    const { query, topK, fusion, useServerWeight, weightBm25 } = this.form.getRawValue();

    this.searchApi
      .search({ query, topK, fusion, weightBm25: useServerWeight ? null : weightBm25 })
      .subscribe({
        next: (response) => {
          this.response.set(response);
          this.pending.set(false);
        },
        error: () => {
          // 503 here means the corpus was never ingested — the snackbar carries the
          // server's own "Le corpus juridique n'est pas indexé." which says exactly that.
          this.response.set(null);
          this.pending.set(false);
        },
      });
  }
}
