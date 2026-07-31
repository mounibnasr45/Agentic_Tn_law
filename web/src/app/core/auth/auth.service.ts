import { Injectable, inject } from '@angular/core';
import { Observable, catchError, finalize, of, shareReplay, switchMap, tap, throwError } from 'rxjs';
import { AuthApi } from '../api/auth.api';
import { Credentials, TokenPair, User } from '../api/api.types';
import { AuthStore } from './auth.store';
import { TokenStorage } from './token.storage';

/**
 * Every operation that changes the session.
 *
 * Deliberately does NOT inject Router: navigation is the caller's decision, and keeping it
 * out means the single-flight test below needs no router double.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(AuthApi);
  private readonly tokens = inject(TokenStorage);
  private readonly store = inject(AuthStore);

  /**
   * The one refresh currently in flight, or null.
   *
   * This single field is the entire fix for the concurrency bug described in refreshOnce().
   */
  private inFlightRefresh: Observable<TokenPair> | null = null;

  login(credentials: Credentials): Observable<User> {
    return this.api.login(credentials).pipe(
      tap((pair) => this.tokens.save(pair)),
      switchMap(() => this.loadUser()),
    );
  }

  register(credentials: Credentials): Observable<User> {
    return this.api.register(credentials).pipe(
      tap((pair) => this.tokens.save(pair)),
      switchMap(() => this.loadUser()),
    );
  }

  loadUser(): Observable<User> {
    return this.api.me().pipe(tap((user) => this.store.setUser(user)));
  }

  /**
   * Best-effort. The local session is cleared FIRST and unconditionally: a logout that can
   * fail is a logout users will skip, and leaving valid tokens in localStorage because the
   * network blipped is the worse outcome. The server call is idempotent.
   */
  logout(): Observable<void> {
    const refreshToken = this.tokens.refreshToken();
    this.clearSession();

    if (!refreshToken) {
      return of(void 0);
    }
    return this.api.logout(refreshToken).pipe(catchError(() => of(void 0)));
  }

  clearSession(): void {
    this.tokens.clear();
    this.store.setUser(null);
  }

  /**
   * Refresh the token pair, guaranteeing AT MOST ONE request is ever in flight.
   *
   * ── Why this is not just `api.refresh(...)` ──────────────────────────────────────────
   *
   * The backend revokes the presented refresh token on every rotation, and treats a second
   * presentation of an already-revoked token as a replay attack — which revokes the user's
   * ENTIRE token chain (see TokenReplayDetected in app/core/errors.py). That is correct
   * server design, and it is lethal to a naive client.
   *
   * Loading the chat page fires /auth/me, /conversations and /health concurrently. If the
   * access token has just expired, all three return 401 at the same moment. Three
   * independent refresh calls then go out carrying the SAME refresh token. The first wins
   * and revokes it; the other two are, from the server's point of view, indistinguishable
   * from an attacker replaying a stolen token — so it destroys the session. The user is
   * thrown back to the login screen for the crime of opening a page.
   *
   * `shareReplay` is what fixes it: the first caller starts the request, every caller
   * during that window subscribes to the same observable, and one HTTP call serves all of
   * them. `finalize` clears the field afterwards so the NEXT expiry can refresh again —
   * without it, the session gets exactly one refresh per page load and then silently dies.
   *
   * A single-request test cannot catch any of this. See auth.service.spec.ts.
   */
  refreshOnce(): Observable<TokenPair> {
    if (this.inFlightRefresh) {
      return this.inFlightRefresh;
    }

    const refreshToken = this.tokens.refreshToken();
    if (!refreshToken) {
      return throwError(() => new Error('No refresh token; the session cannot be renewed.'));
    }

    this.inFlightRefresh = this.api.refresh(refreshToken).pipe(
      tap((pair) => this.tokens.save(pair)),
      catchError((error: unknown) => {
        // Expired, already used, or the chain was revoked. All three mean the same thing
        // to us: this session is over and the user must log in again.
        this.clearSession();
        return throwError(() => error);
      }),
      finalize(() => {
        this.inFlightRefresh = null;
      }),
      // MUST be last: it multicasts everything above it, so all subscribers share the one
      // HTTP request rather than each triggering their own.
      shareReplay({ bufferSize: 1, refCount: false }),
    );

    return this.inFlightRefresh;
  }
}
