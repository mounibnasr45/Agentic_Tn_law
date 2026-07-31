import { Injectable, computed, inject, signal } from '@angular/core';
import { User } from '../api/api.types';
import { TokenStorage } from './token.storage';

/**
 * Who is logged in. State only — every operation that CHANGES it lives in AuthService.
 *
 * Components read `user()` and `isAuthenticated()`; they cannot write either, because the
 * writers are private and only exposed through `asReadonly()`. One place can change the
 * session, which is the same instinct as keeping writes inside a repository.
 */
@Injectable({ providedIn: 'root' })
export class AuthStore {
  private readonly tokens = inject(TokenStorage);

  private readonly _user = signal<User | null>(null);

  /** The profile from GET /api/auth/me. null until it has been fetched. */
  readonly user = this._user.asReadonly();

  /**
   * Derived from the REFRESH token, deliberately — not from `user()` and not from the
   * access token.
   *
   * Not `user()`: on a page reload we have tokens in localStorage but have not yet called
   * /auth/me, so keying off the profile would bounce a logged-in user to /login for the
   * duration of one request, every reload.
   *
   * Not the access token: it expires after 15 minutes while the session is still perfectly
   * alive — the refresh token is what actually says "this session can continue".
   */
  readonly isAuthenticated = computed(() => this.tokens.refreshToken() !== null);

  setUser(user: User | null): void {
    this._user.set(user);
  }
}
