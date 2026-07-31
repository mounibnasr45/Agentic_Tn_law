import { Pipe, PipeTransform, SecurityContext, inject } from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';
import { marked } from 'marked';

/**
 * Renders an LLM answer's markdown to HTML.
 *
 * The model returns markdown — bold article references, numbered lists of conditions,
 * paragraph breaks. Rendering it as plain text (which is what `white-space: pre-wrap`
 * did) leaves `**Article 264**` and `1.` literals on screen in a product whose entire
 * value proposition is legible legal reasoning.
 *
 * SECURITY: this output originates from an LLM, which is untrusted input. We pass the
 * generated HTML through Angular's DomSanitizer in SecurityContext.HTML, which strips
 * <script>, event-handler attributes and javascript: URLs. `bypassSecurityTrustHtml` is
 * deliberately NOT used — it would disable exactly the protection that matters here.
 */
@Pipe({ name: 'markdown' })
export class MarkdownPipe implements PipeTransform {
  private readonly sanitizer = inject(DomSanitizer);

  transform(value: string | null | undefined): string {
    if (!value) {
      return '';
    }

    const html = marked.parse(value, {
      async: false,
      // Treat a single newline as a line break. Models emit prose with single newlines and
      // strict markdown would silently join those lines into one paragraph.
      breaks: true,
      gfm: true,
    });

    return this.sanitizer.sanitize(SecurityContext.HTML, html) ?? '';
  }
}
