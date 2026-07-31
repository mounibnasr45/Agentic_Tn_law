import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { API_BASE } from '../api/api-base';
import { TokenStorage } from './token.storage';

/**
 * Attaches the access token to our own API calls.
 *
 * The `API_BASE` check is not decoration: without it, every request this app ever makes —
 * including to any third-party URL added later — would carry the user's bearer token in a
 * header. Scope the credential to the origin that issued it.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(API_BASE)) {
    return next(req);
  }

  const token = inject(TokenStorage).accessToken();
  if (!token) {
    return next(req);
  }

  // HttpRequest is immutable; clone() is the only way to modify one.
  return next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};
