import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE } from './api-base';
import { Credentials, TokenPair, User } from './api.types';

/**
 * Thin transport over `/api/auth/*`. No state and no token handling — those belong to
 * TokenStorage and AuthService, so this stays trivially mockable in tests.
 */
@Injectable({ providedIn: 'root' })
export class AuthApi {
  private readonly http = inject(HttpClient);

  register(credentials: Credentials): Observable<TokenPair> {
    return this.http.post<TokenPair>(`${API_BASE}/auth/register`, credentials);
  }

  login(credentials: Credentials): Observable<TokenPair> {
    return this.http.post<TokenPair>(`${API_BASE}/auth/login`, credentials);
  }

  /**
   * Exchanges a refresh token for a NEW pair; the presented token is revoked server-side.
   *
   * Never call this directly from a component or an interceptor — go through
   * `AuthService.refreshOnce()`, which guarantees only one of these is ever in flight.
   * Two concurrent calls with the same token look exactly like a replay attack to the
   * backend, and it responds by revoking the entire session.
   */
  refresh(refreshToken: string): Observable<TokenPair> {
    return this.http.post<TokenPair>(`${API_BASE}/auth/refresh`, {
      refresh_token: refreshToken,
    });
  }

  /** 204 and idempotent: an unknown or already-revoked token is not an error. */
  logout(refreshToken: string): Observable<void> {
    return this.http.post<void>(`${API_BASE}/auth/logout`, {
      refresh_token: refreshToken,
    });
  }

  me(): Observable<User> {
    return this.http.get<User>(`${API_BASE}/auth/me`);
  }
}
