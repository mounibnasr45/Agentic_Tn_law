import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE } from './api-base';
import { HealthResponse } from './api.types';

@Injectable({ providedIn: 'root' })
export class HealthApi {
  private readonly http = inject(HttpClient);

  /**
   * Liveness AND readiness. `status` is "ok" only when the database is reachable and the
   * corpus is actually indexed — a running container with an empty corpus reports
   * "degraded", which is what drives the warning banner in the UI.
   *
   * Unauthenticated, so it works on the login screen too.
   */
  health(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${API_BASE}/health`);
  }
}
