import { BreakpointObserver } from '@angular/cdk/layout';
import { UpperCasePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { map } from 'rxjs';
import { AuthService } from './core/auth/auth.service';
import { AuthStore } from './core/auth/auth.store';
import { I18nService } from './core/i18n/i18n.service';
import { ThemeService } from './core/theme/theme.service';

@Component({
  selector: 'app-root',
  imports: [
    UpperCasePipe,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly breakpoints = inject(BreakpointObserver);

  protected readonly store = inject(AuthStore);
  protected readonly theme = inject(ThemeService);
  protected readonly t = inject(I18nService);

  /**
   * Five nav links plus the brand mark, both toggles and the auth controls never fit a
   * phone-width toolbar. The old fix — a horizontally-scrolling nav strip — left "Search",
   * "Evaluation" and "Status" scrolled off-screen with no visual hint a swipe would reveal
   * them, so on a real phone they were effectively missing. A menu button is the pattern
   * users already know for "more navigation lives here" and shows every link at once,
   * full text, no discovery problem.
   */
  protected readonly isHandset = toSignal(
    this.breakpoints.observe('(max-width: 640px)').pipe(map((state) => state.matches)),
    { initialValue: false },
  );

  protected readonly themeIcon = computed(() => {
    switch (this.theme.preference()) {
      case 'light':
        return 'light_mode';
      case 'dark':
        return 'dark_mode';
      default:
        return 'brightness_auto';
    }
  });

  // Reads t.s() so the tooltip re-computes when the language changes, not only when the
  // theme does.
  protected readonly themeLabel = computed(() => {
    const s = this.t.s();
    switch (this.theme.preference()) {
      case 'light':
        return s.themeLight;
      case 'dark':
        return s.themeDark;
      default:
        return s.themeSystem;
    }
  });

  constructor() {
    // After a reload the tokens are still in localStorage but the in-memory profile is
    // empty, so re-fetch it. If the access token expired while the tab was closed this
    // request 401s, the refresh interceptor renews the pair, and the retry succeeds —
    // invisibly. That round trip is the entire reason /api/auth/refresh exists, and it is
    // exactly what the Streamlit client never did.
    if (this.store.isAuthenticated() && this.store.user() === null) {
      this.auth.loadUser().subscribe({
        error: () => {
          // Already handled: the refresh interceptor clears the session and redirects.
        },
      });
    }
  }

  protected logout(): void {
    this.auth.logout().subscribe(() => {
      void this.router.navigate(['/login']);
    });
  }
}
