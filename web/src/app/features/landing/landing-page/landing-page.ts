import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { CorpusDocument } from '../../../core/api/api.types';
import { PublicApi } from '../../../core/api/public.api';
import { I18nService } from '../../../core/i18n/i18n.service';

/**
 * A curated one-line description per source document, keyed by the exact filename the
 * backend stores as `title`. Deliberately NOT server-provided: the backend's job is
 * confirming what is actually indexed (title, live chunk count) — text explaining what a
 * law covers to a visitor deciding whether to sign up is editorial content, not corpus
 * metadata, and belongs in the layer that owns copy.
 *
 * A title with no entry here still renders (via the `??` fallback in the template), so
 * adding a fourth document to the corpus cannot break this page — it just ships without a
 * description until this map is updated.
 */
const DOCUMENT_DESCRIPTIONS: Record<string, { fr: string; en: string }> = {
  'Constitution_fr.pdf': {
    fr: "La Constitution de la République tunisienne : l'organisation des pouvoirs publics, les droits et libertés fondamentaux, et les principes fondateurs de l'État.",
    en: "The Constitution of the Republic of Tunisia: the organisation of public powers, fundamental rights and freedoms, and the founding principles of the state.",
  },
  'penal_code.pdf': {
    fr: 'Le Code Pénal tunisien : les infractions, leur qualification, et les peines encourues — crimes, délits et contraventions prévus par le droit tunisien.',
    en: "The Tunisian Penal Code: offences, how they are classified, and the penalties attached to them — crimes, misdemeanours and minor offences under Tunisian law.",
  },
  'loi relatif à la liberté de la presse.pdf': {
    fr: "Le décret-loi n° 2011-115 du 2 novembre 2011, relatif à la liberté de la presse, de l'impression et de l'édition en Tunisie.",
    en: "Decree-law No. 2011-115 of 2 November 2011, on the freedom of the press, printing and publishing in Tunisia.",
  },
};

@Component({
  selector: 'app-landing-page',
  imports: [DecimalPipe, MatButtonModule, MatIconModule, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './landing-page.html',
  styleUrl: './landing-page.scss',
})
export class LandingPage {
  protected readonly t = inject(I18nService);

  private readonly api = inject(PublicApi);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly documents = signal<CorpusDocument[]>([]);
  protected readonly loading = signal(true);
  protected readonly failed = signal(false);

  constructor() {
    this.api
      .corpusOverview()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (documents) => {
          this.documents.set(documents);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.failed.set(true);
        },
      });
  }

  protected description(document: CorpusDocument): string {
    const entry = DOCUMENT_DESCRIPTIONS[document.title];
    return entry ? entry[this.t.current()] : '';
  }
}
