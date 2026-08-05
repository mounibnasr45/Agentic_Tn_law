import { BreakpointObserver } from '@angular/cdk/layout';
import { DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { map } from 'rxjs';
import { CorpusDocument } from '../../../core/api/api.types';
import { DocumentsApi } from '../../../core/api/documents.api';
import { I18nService } from '../../../core/i18n/i18n.service';

/**
 * Read the sources, in the app, without downloading them first.
 *
 * WHY THIS PAGE EXISTS. An answer that cites "Article 258 du code pénal" is only as
 * trustworthy as the reader's ability to go and check it, and until now the corpus was
 * visible only as 400-character excerpts inside citation cards. Verifying a citation meant
 * finding the PDF yourself — enough friction that people stop checking and start trusting
 * the model, which is the failure mode a citation-grounded assistant exists to prevent.
 *
 * The preview is the browser's own PDF viewer, deliberately: it already has search, zoom,
 * page navigation and printing, all of which a hand-rolled canvas viewer would have to
 * reimplement worse, and it costs no bundle size.
 */
@Component({
  selector: 'app-documents-page',
  imports: [DecimalPipe, MatButtonModule, MatIconModule, MatProgressBarModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './documents-page.html',
  styleUrl: './documents-page.scss',
})
export class DocumentsPage {
  private readonly api = inject(DocumentsApi);

  protected readonly t = inject(I18nService);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly destroyRef = inject(DestroyRef);
  private readonly breakpoints = inject(BreakpointObserver);

  /**
   * Mobile Chrome (and most mobile browsers) cannot reliably render a PDF blob inline in
   * an <iframe> — it falls back to its own native "file ready" interstitial rendered
   * WITHIN the iframe's box, which is a small floating card with a generic filename and an
   * "Open" button, not a broken layout this component's CSS can reach or fix. Below this
   * width the template skips the iframe entirely and shows a plain "open in a new tab"
   * panel instead, which every mobile browser handles correctly with its own full PDF
   * viewer — a better mobile experience than a cramped iframe would have been anyway.
   */
  protected readonly isHandset = toSignal(
    this.breakpoints.observe('(max-width: 640px)').pipe(map((state) => state.matches)),
    { initialValue: false },
  );

  protected readonly documents = signal<CorpusDocument[]>([]);
  protected readonly selected = signal<CorpusDocument | null>(null);
  protected readonly previewUrl = signal<SafeResourceUrl | null>(null);
  protected readonly loading = signal(true);
  protected readonly previewLoading = signal(false);
  protected readonly failed = signal(false);

  /**
   * The raw object URL behind previewUrl. Kept separately because revoking needs the
   * string, and SafeResourceUrl deliberately does not give it back — without this the
   * blobs leak for the lifetime of the tab, one per document the user opens.
   */
  private objectUrl: string | null = null;

  constructor() {
    this.api
      .list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (documents) => {
          this.documents.set(documents);
          this.loading.set(false);
          // Open the first one straight away: a viewer whose first screen is an empty
          // pane asks the reader to do work before showing them anything.
          if (documents.length > 0) {
            this.select(documents[0]);
          }
        },
        error: () => {
          this.loading.set(false);
          this.failed.set(true);
        },
      });

    this.destroyRef.onDestroy(() => this.releaseObjectUrl());
  }

  private releaseObjectUrl(): void {
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }
  }

  protected select(document: CorpusDocument): void {
    if (this.selected()?.id === document.id && this.previewUrl()) {
      return;
    }

    this.selected.set(document);
    this.previewLoading.set(true);
    this.previewUrl.set(null);

    this.api
      .file(document.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (blob) => {
          // Revoke only once the replacement has arrived — revoking up front would blank
          // the pane for the whole round trip.
          this.releaseObjectUrl();
          this.objectUrl = URL.createObjectURL(blob);
          // bypassSecurityTrustResourceUrl is safe here and nowhere near arbitrary: the
          // URL is one this code just minted from a blob it fetched itself, not anything
          // the server or the user supplied.
          this.previewUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.objectUrl));
          this.previewLoading.set(false);
        },
        error: () => {
          this.previewLoading.set(false);
          this.failed.set(true);
        },
      });
  }

  /** The mobile fallback: a real browser tab and its native PDF viewer, not an iframe. */
  protected openInNewTab(): void {
    if (this.objectUrl) {
      window.open(this.objectUrl, '_blank');
    }
  }

  protected download(document: CorpusDocument): void {
    this.api
      .file(document.id, true)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((blob) => {
        // A separate, short-lived object URL rather than reusing the preview's: the
        // preview's is still mounted in the iframe, and revoking it here would blank it.
        const url = URL.createObjectURL(blob);
        const anchor = window.document.createElement('a');
        anchor.href = url;
        anchor.download = document.title;
        anchor.click();
        URL.revokeObjectURL(url);
      });
  }

  protected sizeInMb(bytes: number): number {
    return bytes / 1024 / 1024;
  }
}
