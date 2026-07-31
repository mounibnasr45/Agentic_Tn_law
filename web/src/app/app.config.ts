import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { routes } from './app.routes';
import { authInterceptor } from './core/auth/auth.interceptor';
import { refreshInterceptor } from './core/auth/refresh.interceptor';
import { httpErrorInterceptor } from './core/errors/http-error.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),

    // withComponentInputBinding lets a route param arrive as a component input, so ChatPage
    // declares `conversationId = input<string>()` instead of subscribing to ActivatedRoute.
    provideRouter(routes, withComponentInputBinding()),

    provideHttpClient(
      // ORDER IS LOAD-BEARING. Interceptors wrap each other in array order, so the first is
      // outermost and sees the response last:
      //
      //   request    httpError -> auth -> refresh -> network
      //   response   httpError <- auth <- refresh <- network
      //
      // httpError is outermost so it observes the FINAL outcome. Registered innermost
      // instead, every expired access token would flash an error at the user a moment
      // before the refresh-and-retry quietly succeeded.
      withInterceptors([httpErrorInterceptor, authInterceptor, refreshInterceptor]),
    ),
  ],
};
