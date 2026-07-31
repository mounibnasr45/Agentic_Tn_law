import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from './core/auth/auth.service';
import { AuthStore } from './core/auth/auth.store';
import { ThemeService } from './core/theme/theme.service';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly store = inject(AuthStore);
  protected readonly theme = inject(ThemeService);

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

  protected readonly themeLabel = computed(() => {
    switch (this.theme.preference()) {
      case 'light':
        return 'Thème clair — cliquer pour le thème sombre';
      case 'dark':
        return 'Thème sombre — cliquer pour suivre le système';
      default:
        return 'Thème système — cliquer pour le thème clair';
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
