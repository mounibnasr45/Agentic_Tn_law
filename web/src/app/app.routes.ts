import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/auth/auth.guards';

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
    // Unauthenticated on purpose: "is the service up?" must be answerable when you cannot
    // log in, which is exactly when you most want to ask it.
    path: 'status',
    title: 'État du service · Agent Juridique Tunisien',
    loadComponent: () =>
      import('./features/status/status-page/status-page').then((m) => m.StatusPage),
  },

  { path: '**', redirectTo: 'chat' },
];
