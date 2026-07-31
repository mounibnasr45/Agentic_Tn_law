import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { ApiErrorBody } from '../api/api.types';
import { Notifications } from './notifications';

/**
 * Surfaces failures to the user.
 *
 * MUST be registered FIRST in `withInterceptors([...])`. Interceptors wrap each other in
 * array order, so the first is the outermost and sees the FINAL outcome — after
 * refreshInterceptor has had its chance to renew the token and replay the request. Register
 * it last and every expired access token would flash an error at the user a moment before
 * the retry quietly succeeded.
 */
export const httpErrorInterceptor: HttpInterceptorFn = (req, next) => {
  const notifications = inject(Notifications);

  return next(req).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse) {
        notifications.error(messageFor(error));
      }
      return throwError(() => error);
    }),
  );
};

/**
 * Prefer the server's own message.
 *
 * `app/core/errors.py` already maps each DomainError to a precise French sentence —
 * "OPENROUTER_API_KEY invalide ou révoquée." is far more useful than anything a generic
 * status-code table could produce. We only invent a message when there isn't one.
 */
function messageFor(error: HttpErrorResponse): string {
  const detail = (error.error as ApiErrorBody | null | undefined)?.detail;

  // FastAPI's 422 puts an ARRAY of validation objects in `detail`, not a string — hence
  // the type check rather than a truthiness check.
  if (typeof detail === 'string' && detail.trim().length > 0) {
    return detail;
  }

  switch (error.status) {
    case 0:
      // No HTTP response at all: the backend is down, DNS failed, or the browser blocked it.
      return "Service injoignable. Vérifiez que l'API est démarrée.";
    case 401:
      // Reaching here means the refresh interceptor already tried and failed.
      return 'Session expirée. Veuillez vous reconnecter.';
    case 422:
      return 'Requête invalide.';
    case 429:
      return 'Trop de requêtes. Réessayez dans un instant.';
    case 504:
      return "Le serveur a mis trop de temps à répondre. L'agent est peut-être surchargé.";
    default:
      return `Erreur inattendue (${error.status}).`;
  }
}
