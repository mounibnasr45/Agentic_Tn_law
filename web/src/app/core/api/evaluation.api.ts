import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE } from './api-base';
import { EvaluationResponse } from './api.types';

/**
 * The retrieval evaluation results.
 *
 * Unauthenticated, like /health: these are published measurements about a public corpus,
 * and requiring a login to read them would defeat the point of publishing them.
 */
@Injectable({ providedIn: 'root' })
export class EvaluationApi {
  private readonly http = inject(HttpClient);

  results(): Observable<EvaluationResponse> {
    return this.http.get<EvaluationResponse>(`${API_BASE}/evaluation`);
  }
}
