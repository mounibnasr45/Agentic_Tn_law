import { Injectable, signal } from '@angular/core';
import { TokenPair } from '../api/api.types';

const ACCESS_KEY = 'atl.access_token';
const REFRESH_KEY = 'atl.refresh_token';

/**
 * Holds the JWT pair, mirrored into localStorage so a page reload does not log you out.
 *
 * SECURITY TRADEOFF, STATED PLAINLY: localStorage is readable by any JavaScript running on
 * this origin, so a successful XSS steals both tokens. The genuinely safer design is an
 * httpOnly, Secure, SameSite=Strict cookie that JavaScript cannot read at all — but that is
 * not available to us here, because `/api/auth/login` returns the pair in a JSON *body*
 * (see `TokenPair` in app/api/schemas/auth.py). Moving to cookies is a backend change:
 * FastAPI would need to `Set-Cookie` on login/refresh, and we would then need CSRF
 * protection, which the bearer-token design does not require.
 *
 * What limits the damage in the meantime is the backend, not this file: access tokens live
 * 15 minutes, refresh tokens rotate on every use, and a replayed refresh token revokes the
 * whole chain. A stolen access token is useful briefly; a stolen refresh token gets caught
 * the moment the real client next refreshes.
 */
@Injectable({ providedIn: 'root' })
export class TokenStorage {
  private readonly _accessToken = signal<string | null>(read(ACCESS_KEY));
  private readonly _refreshToken = signal<string | null>(read(REFRESH_KEY));

  readonly accessToken = this._accessToken.asReadonly();
  readonly refreshToken = this._refreshToken.asReadonly();

  save(pair: TokenPair): void {
    this._accessToken.set(pair.access_token);
    this._refreshToken.set(pair.refresh_token);
    write(ACCESS_KEY, pair.access_token);
    write(REFRESH_KEY, pair.refresh_token);
  }

  clear(): void {
    this._accessToken.set(null);
    this._refreshToken.set(null);
    write(ACCESS_KEY, null);
    write(REFRESH_KEY, null);
  }
}

/**
 * localStorage throws rather than returning null in Safari private mode and when a browser
 * blocks third-party storage. A storage failure should degrade the session to
 * in-memory-only, not crash the application at construction time.
 */
function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, value);
    }
  } catch {
    // Ignored deliberately: the signals above remain the source of truth for this tab.
  }
}
