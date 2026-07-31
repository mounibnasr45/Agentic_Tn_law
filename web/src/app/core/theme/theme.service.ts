import { Injectable, effect, signal } from '@angular/core';

export type ThemePreference = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'atl.theme';

/**
 * Light/dark switching, driven entirely by the CSS `color-scheme` property.
 *
 * Angular Material 3's `mat.theme()` emits its system variables through `light-dark()`, so
 * setting `color-scheme` is all that is needed — there is no second stylesheet and no
 * class to toggle on every component. `light dark` (the default) defers to the operating
 * system; the explicit values override it.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly preference = signal<ThemePreference>(restore());

  constructor() {
    effect(() => {
      const preference = this.preference();
      document.documentElement.style.colorScheme =
        preference === 'system' ? 'light dark' : preference;

      try {
        localStorage.setItem(STORAGE_KEY, preference);
      } catch {
        // Storage can be unavailable (private mode). The theme still applies for this tab.
      }
    });
  }

  /** Cycles system → light → dark → system. */
  cycle(): void {
    this.preference.update((current) =>
      current === 'system' ? 'light' : current === 'light' ? 'dark' : 'system',
    );
  }
}

function restore(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark' || stored === 'system') {
      return stored;
    }
  } catch {
    // ignored — fall through to the system default
  }
  return 'system';
}
