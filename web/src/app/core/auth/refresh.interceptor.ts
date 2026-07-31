import {
  HttpContextToken,
  HttpErrorResponse,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { API_BASE } from '../api/api-base';
import { AuthService } from './auth.service';
import { TokenStorage } from './token.storage';

/**
 * Marks a request that has already been retried once after a refresh.
 *
 * Without it: the retry 401s for some unrelated reason, which triggers another refresh,
 * which retries again, forever. `HttpContext` is the typed, per-request way to carry this
 * — a custom header would be sent to the server, which has no business seeing it.
 */
const ALREADY_RETRIED = new HttpContextToken<boolean>(() => false);

/**
 * On 401, renew the session once and replay the request.
 *
 * The interesting part is not here — it is `AuthService.refreshOnce()`, which guarantees
 * that N concurrent 401s produce exactly ONE refresh call. Read the comment there; it
 * explains why the obvious implementation logs the user out.
 */
export const refreshInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const tokens = inject(TokenStorage);
  const router = inject(Router);

  return next(req).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse) || error.status !== 401) {
        return throwError(() => error);
      }

      // Already retried, not a refreshable endpoint, or no session to renew — in all three
      // cases a refresh either cannot help or would loop.
      if (
        req.context.get(ALREADY_RETRIED) ||
        !isRefreshable(req.url) ||
        tokens.refreshToken() === null
      ) {
        return throwError(() => error);
      }

      return auth.refreshOnce().pipe(
        // Placed BEFORE switchMap on purpose: it must see failures of the REFRESH only.
        // After the switchMap it would also catch a failure of the replayed request, and
        // a 500 from /api/ask would log the user out.
        catchError((refreshError: unknown) => {
          auth.clearSession();
          void router.navigate(['/login']);
          return throwError(() => refreshError);
        }),
        switchMap(() => next(replay(req, tokens.accessToken()))),
      );
    }),
  );
};

/**
 * A 401 from these means "your credentials are wrong" or "your refresh token is dead" —
 * never "your access token aged out" — so refreshing is either pointless or recursive.
 * `/auth/me` is the exception: it is an ordinary authenticated call that legitimately 401s
 * on an expired access token.
 */
function isRefreshable(url: string): boolean {
  if (!url.startsWith(`${API_BASE}/auth/`)) {
    return true;
  }
  return url.startsWith(`${API_BASE}/auth/me`);
}

/**
 * Re-issue the request with the freshly-minted token.
 *
 * The header is set explicitly rather than relying on `authInterceptor` running again:
 * `next()` continues DOWN the chain from here, so interceptors registered before this one
 * do not re-execute. Depending on their order would make this correct only by accident.
 */
function replay(req: HttpRequest<unknown>, accessToken: string | null): HttpRequest<unknown> {
  const context = req.context.set(ALREADY_RETRIED, true);

  return accessToken === null
    ? req.clone({ context })
    : req.clone({ context, setHeaders: { Authorization: `Bearer ${accessToken}` } });
}
