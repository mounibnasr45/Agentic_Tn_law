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

/**
 * Keeps non-admins off the corpus screen.
 *
 * SAME CAVEAT, AND IT MATTERS MORE HERE: this is not a security boundary. It runs in
 * JavaScript the user controls. The enforcement is `CurrentAdmin` in app/api/deps.py,
 * which re-checks is_admin on every single admin request — so bypassing this guard gets
 * you a rendered page whose every API call returns 403.
 *
 * Redirects to /chat rather than /login: an authenticated non-admin is not missing a
 * session, they are simply somewhere they have no business being, and bouncing them to a
 * login form they have already completed is a confusing dead end.
 */
export const adminGuard: CanActivateFn = () => {
  const router = inject(Router);
  const store = inject(AuthStore);

  if (!store.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  // user() is null on a hard page load until /auth/me resolves. Treating that as "not an
  // admin" would bounce an admin off their own page on every refresh, so the ambiguous
  // case is allowed through and left to the server's 403 — which is the authority anyway.
  const user = store.user();
  return user === null || user.is_admin ? true : router.createUrlTree(['/chat']);
};
