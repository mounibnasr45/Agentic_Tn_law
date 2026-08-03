import { Routes } from '@angular/router';
import { adminGuard, authGuard, guestGuard } from './core/auth/auth.guards';

/**
 * `loadComponent` is a lazy import: each page becomes its own chunk, downloaded the first
 * time someone navigates to it. A visitor who only logs in never pays for the search
 * explorer's JavaScript.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'chat' },

  {
    path: 'login',
    title: 'Connexion · Agent Juridique Tunisien',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login-page/login-page').then((m) => m.LoginPage),
  },

  {
    path: 'chat',
    title: 'Agent Juridique Tunisien',
    canActivate: [authGuard],
    loadComponent: () => import('./features/chat/chat-page/chat-page').then((m) => m.ChatPage),
  },
  {
    // Same component. The id arrives as a component input thanks to
    // withComponentInputBinding, which is what makes a conversation deep-linkable — a thing
    // the Streamlit version could not do at all.
    path: 'chat/:conversationId',
    title: 'Agent Juridique Tunisien',
    canActivate: [authGuard],
    loadComponent: () => import('./features/chat/chat-page/chat-page').then((m) => m.ChatPage),
  },

  {
    path: 'search',
    title: 'Explorateur de recherche · Agent Juridique Tunisien',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/search/search-page/search-page').then((m) => m.SearchPage),
  },

  {
    path: 'admin',
    title: 'Corpus · Agent Juridique Tunisien',
    // BOTH guards, in order: authGuard sends a logged-out visitor to /login, adminGuard
    // sends a logged-in non-admin to /chat. Neither is a security boundary — CurrentAdmin
    // in app/api/deps.py re-checks is_admin on every request this page makes.
    canActivate: [authGuard, adminGuard],
    loadComponent: () =>
      import('./features/admin/admin-page/admin-page').then((m) => m.AdminPage),
  },

  {
    // Unauthenticated, like /status: these are published measurements about a public
    // corpus. Putting them behind a login would defeat the point of publishing them.
    path: 'evaluation',
    title: 'Évaluation · Agent Juridique Tunisien',
    loadComponent: () =>
      import('./features/evaluation/evaluation-page/evaluation-page').then(
        (m) => m.EvaluationPage,
      ),
  },

  {
    // Unauthenticated on purpose: "is the service up?" must be answerable when you cannot
    // log in, which is exactly when you most want to ask it.
    path: 'status',
    title: 'État du service · Agent Juridique Tunisien',
    loadComponent: () =>
      import('./features/status/status-page/status-page').then((m) => m.StatusPage),
  },

  { path: '**', redirectTo: 'chat' },
];
