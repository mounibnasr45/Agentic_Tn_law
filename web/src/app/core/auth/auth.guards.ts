import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthStore } from './auth.store';

/**
 * Keeps logged-out visitors off the authenticated pages.
 *
 * THIS IS NOT A SECURITY BOUNDARY. It runs in the browser, in JavaScript the user controls;
 * anyone can bypass it with devtools. All it does is stop an empty chat shell rendering for
 * someone with no session. The enforcement that matters is `CurrentUser` in
 * app/api/deps.py, server-side, where every protected route already rejects a missing or
 * invalid token.
 */
export const authGuard: CanActivateFn = () => {
  const router = inject(Router);
  return inject(AuthStore).isAuthenticated() || router.createUrlTree(['/login']);
};

/** The inverse: an already-logged-in user has no use for the login form. */
export const guestGuard: CanActivateFn = () => {
  const router = inject(Router);
  return !inject(AuthStore).isAuthenticated() || router.createUrlTree(['/chat']);
};
