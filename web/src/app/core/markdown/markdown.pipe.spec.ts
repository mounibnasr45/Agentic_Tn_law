import { TestBed } from '@angular/core/testing';
import { MarkdownPipe } from './markdown.pipe';

describe('MarkdownPipe', () => {
  let pipe: MarkdownPipe;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [MarkdownPipe] });
    pipe = TestBed.inject(MarkdownPipe);
  });

  it('renders the markdown a legal answer actually contains', () => {
    const html = pipe.transform('Selon l’**article 264**, la peine est :\n\n1. un an\n2. une amende');

    expect(html).toContain('<strong>article 264</strong>');
    expect(html).toContain('<ol>');
    expect(html).toContain('<li>');
  });

  it('keeps single newlines as line breaks', () => {
    // Models write prose with single newlines; strict markdown would join these into one
    // paragraph and the answer would read as a wall of text.
    expect(pipe.transform('ligne un\nligne deux')).toContain('<br>');
  });

  /**
   * The security case. This content comes from an LLM, which can be steered by whatever is
   * in the retrieved corpus — so it is untrusted input rendered via [innerHTML].
   */
  it('strips script tags from model output', () => {
    const html = pipe.transform('Bonjour <script>alert("xss")</script> au revoir');

    expect(html).not.toContain('<script');
    expect(html).not.toContain('alert(');
  });

  it('strips inline event handlers', () => {
    const html = pipe.transform('<img src="x" onerror="alert(1)">');

    expect(html).not.toContain('onerror');
  });

  it('neutralises javascript: URLs', () => {
    const html = pipe.transform('[cliquez ici](javascript:alert(1))');

    // Angular does not delete the URL — it rewrites the scheme to `unsafe:`, which no
    // browser will execute. Asserting the string "javascript:" is simply absent would be
    // wrong: what matters is that it is no longer a scheme the browser acts on.
    expect(html).toContain('unsafe:javascript:');
    expect(html).not.toContain('href="javascript:');
  });

  it('returns an empty string for null, undefined and empty input', () => {
    expect(pipe.transform(null)).toBe('');
    expect(pipe.transform(undefined)).toBe('');
    expect(pipe.transform('')).toBe('');
  });
});
