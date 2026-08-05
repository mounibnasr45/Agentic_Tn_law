import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE } from './api-base';
import { CorpusDocument } from './api.types';

/**
 * What a visitor can see before signing up — right now, just the corpus overview.
 *
 * A separate service from DocumentsApi on purpose, thin as it is: DocumentsApi's calls
 * carry an Authorization header via authInterceptor and 401 through refreshInterceptor on
 * an expired token, machinery that makes no sense for an endpoint anyone can call. Landing
 * on the wrong side of that distinction later — adding an authenticated call here, say —
 * would be a silent, easy-to-miss regression; a separate service makes it a compile error
 * choosing the wrong import instead.
 */
@Injectable({ providedIn: 'root' })
export class PublicApi {
  private readonly http = inject(HttpClient);

  corpusOverview(): Observable<CorpusDocument[]> {
    return this.http.get<CorpusDocument[]>(`${API_BASE}/public/corpus`);
  }
}
