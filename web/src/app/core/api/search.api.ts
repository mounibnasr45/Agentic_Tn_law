import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE } from './api-base';
import { FusionStrategy, SearchResponse } from './api.types';

export interface SearchParams {
  query: string;
  topK: number;
  fusion: FusionStrategy;
  /** null = defer to the server's configured HYBRID_WEIGHT_BM25 (0.0, dense-only). */
  weightBm25: number | null;
}

@Injectable({ providedIn: 'root' })
export class SearchApi {
  private readonly http = inject(HttpClient);

  /**
   * Retrieval with no LLM — cheap, deterministic, and the honest way to see what the
   * retriever actually returns without a model paraphrasing over its mistakes.
   *
   * Note the shape: the handler in app/api/routes/search.py declares `query`, `top_k`,
   * `weight_bm25` and `fusion` as plain scalars, so FastAPI reads them as QUERY-STRING
   * parameters even though the verb is POST. The body is empty. Sending them as JSON
   * instead yields a 422 that reads like a validation bug in the backend.
   */
  search(params: SearchParams): Observable<SearchResponse> {
    let httpParams = new HttpParams()
      .set('query', params.query)
      .set('top_k', params.topK)
      .set('fusion', params.fusion);

    // Omitted entirely rather than sent as null — the server treats "absent" as
    // "use the configured default", which is not the same as any number we could send.
    if (params.weightBm25 !== null) {
      httpParams = httpParams.set('weight_bm25', params.weightBm25);
    }

    return this.http.post<SearchResponse>(`${API_BASE}/search`, null, { params: httpParams });
  }
}
