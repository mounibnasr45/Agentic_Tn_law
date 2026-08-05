import { Injectable, computed, signal } from '@angular/core';
import { STRINGS, Strings } from './strings';

export type Language = 'fr' | 'en';

const STORAGE_KEY = 'agentic-tn-law-language';

/**
 * UI language, as a signal.
 *
 * WHY NOT @angular/localize. Angular's built-in i18n is a BUILD-time mechanism: it emits
 * one bundle per locale, which then have to be served from different paths and selected by
 * the server. That is the right answer for a marketing site with ten locales; here it
 * would mean doubling the build, teaching FastAPI to route by Accept-Language, and losing
 * the ability to switch language without a page load. A dictionary behind a signal costs
 * one small file, switches instantly, and keeps a single bundle — which matters when the
 * whole app is served by one container on a free tier.
 *
 * THE LANGUAGE IS ALSO SENT TO THE BACKEND. It is not only a display concern: the agent
 * answers in whichever language is chosen (see app/agent/prompts.py), so this signal is
 * read by ChatApi on every ask. A user reading an English interface being answered in
 * French would be a worse experience than either language alone.
 */
@Injectable({ providedIn: 'root' })
export class I18nService {
  private readonly language = signal<Language>(this.initial());

  /** The active dictionary. Templates read `t.s().someKey`. */
  readonly s = computed<Strings>(() => STRINGS[this.language()]);

  readonly current = this.language.asReadonly();

  private initial(): Language {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'fr' || stored === 'en') {
      return stored;
    }
    // French default, and not merely because the UI was written in French: the corpus is
    // the French text of Tunisian law, so a French speaker is the expected reader. A
    // browser reporting any French locale keeps it; everyone else gets English, which is
    // more useful than a French UI they cannot read.
    return navigator.language?.toLowerCase().startsWith('fr') ? 'fr' : 'en';
  }

  set(language: Language): void {
    this.language.set(language);
    localStorage.setItem(STORAGE_KEY, language);
    // Keeps the document in sync for screen readers and for CSS that keys on :lang().
    document.documentElement.lang = language;
  }

  toggle(): void {
    this.set(this.language() === 'fr' ? 'en' : 'fr');
  }
}
