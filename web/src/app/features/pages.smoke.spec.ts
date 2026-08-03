import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Type } from '@angular/core';
import { provideRouter } from '@angular/router';
import { AdminPage } from './admin/admin-page/admin-page';
import { EvaluationPage } from './evaluation/evaluation-page/evaluation-page';
import { LoginPage } from './auth/login-page/login-page';
import { ChatPage } from './chat/chat-page/chat-page';
import { SearchPage } from './search/search-page/search-page';
import { StatusPage } from './status/status-page/status-page';

/**
 * Render smoke tests for every routed page.
 *
 * `ng build` type-checks templates but never INSTANTIATES a component, so a whole class of
 * failure survives a green build: a Material component used with the wrong API, a missing
 * provider, a signal read during construction that is not yet set. These tests mount each
 * page for real and assert something recognisable reached the DOM.
 *
 * They are not a substitute for opening a browser — no layout, no CSS, no user interaction
 * is exercised here — but they are the difference between "it compiled" and "it runs".
 */
async function mount<T>(component: Type<T>): Promise<ComponentFixture<T>> {
  await TestBed.configureTestingModule({
    imports: [component],
    providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
  }).compileComponents();

  const fixture = TestBed.createComponent(component);
  await fixture.whenStable();
  return fixture;
}

function text(fixture: ComponentFixture<unknown>): string {
  return (fixture.nativeElement as HTMLElement).textContent ?? '';
}

describe('page render smoke tests', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it('LoginPage renders the form and can switch to registration', async () => {
    const fixture = await mount(LoginPage);

    expect(text(fixture)).toContain('Se connecter');
    expect((fixture.nativeElement as HTMLElement).querySelector('input[type="email"]')).toBeTruthy();

    // The mode toggle rewires the password validators (12 chars on register, not on login).
    const toggle = (fixture.nativeElement as HTMLElement).querySelectorAll('button');
    const registerToggle = Array.from(toggle).find((b) => b.textContent?.includes("S'inscrire"));
    registerToggle?.click();
    await fixture.whenStable();

    expect(text(fixture)).toContain('12 caractères minimum');
  });

  it('ChatPage renders its empty state and asks for the conversation list', async () => {
    const fixture = await mount(ChatPage);
    const httpMock = TestBed.inject(HttpTestingController);

    // The sidebar populates itself on construction.
    httpMock.expectOne('/api/conversations').flush([]);
    await fixture.whenStable();

    expect(text(fixture)).toContain('Posez votre première question');
    expect(text(fixture)).toContain('Nouvelle conversation');
    httpMock.verify();
  });

  it('SearchPage renders the retrieval knobs and both fusion strategies', async () => {
    const fixture = await mount(SearchPage);
    const host = fixture.nativeElement as HTMLElement;

    expect(text(fixture)).toContain('Explorateur de recherche');
    // A closed mat-select renders only its SELECTED value in the trigger; the rest of the
    // options do not exist in the DOM until it is opened.
    expect(text(fixture)).toContain('Pondérée');

    host.querySelector<HTMLElement>('.mat-mdc-select-trigger')?.click();
    await fixture.whenStable();

    // Options render into a CDK overlay attached to document.body, NOT inside the fixture.
    const overlay = document.querySelector('.cdk-overlay-container')?.textContent ?? '';
    // Both values the backend's FusionStrategy enum accepts must be offered.
    expect(overlay).toContain('Pondérée');
    expect(overlay).toContain('RRF');
  });

  it('StatusPage renders live health values', async () => {
    const fixture = await mount(StatusPage);
    const httpMock = TestBed.inject(HttpTestingController);

    httpMock.expectOne('/api/health').flush({
      status: 'ok',
      database: true,
      model_loaded: true,
      embedding_model: 'intfloat/multilingual-e5-small',
      corpus_chunks: 712,
    });
    await fixture.whenStable();

    expect(text(fixture)).toContain('712');
    expect(text(fixture)).toContain('intfloat/multilingual-e5-small');
    httpMock.verify();
  });

  it('StatusPage warns when the corpus is empty rather than showing a healthy page', async () => {
    const fixture = await mount(StatusPage);

    TestBed.inject(HttpTestingController)
      .expectOne('/api/health')
      .flush({
        status: 'degraded',
        database: true,
        model_loaded: true,
        embedding_model: 'intfloat/multilingual-e5-small',
        corpus_chunks: 0,
      });
    await fixture.whenStable();

    // "Running" and "able to answer" are different claims — the UI must not conflate them.
    expect(text(fixture)).toContain("Le corpus n'est pas indexé");
  });

  it('AdminPage renders the drop zone and reports the encoder behind the index', async () => {
    const fixture = await mount(AdminPage);
    const httpMock = TestBed.inject(HttpTestingController);

    // The corpus listing is fetched on construction.
    httpMock.expectOne('/api/admin/corpus').flush({
      documents: [
        {
          id: 'd1',
          title: 'penal_code.pdf',
          status: 'indexed',
          chunks_total: 474,
          chunks_done: 474,
          corpus_version: 1,
          error: null,
          created_at: '2026-08-01T10:00:00Z',
          indexed_at: '2026-08-01T10:05:00Z',
          progress: 1,
        },
      ],
      total_chunks: 712,
      embedding_model: 'intfloat/multilingual-e5-small',
      is_ingesting: false,
    });
    await fixture.whenStable();

    expect(text(fixture)).toContain('Glissez un PDF ici');
    expect(text(fixture)).toContain('penal_code.pdf');
    expect(text(fixture)).toContain('474');
    // Bug 13 was invisible because nothing displayed which encoder built the index.
    expect(text(fixture)).toContain('intfloat/multilingual-e5-small');
    httpMock.verify();
  });

  it('AdminPage surfaces a failed ingest with its reason instead of a stuck bar', async () => {
    const fixture = await mount(AdminPage);

    TestBed.inject(HttpTestingController)
      .expectOne('/api/admin/corpus')
      .flush({
        documents: [
          {
            id: 'd2',
            title: 'scan.pdf',
            status: 'failed',
            chunks_total: 0,
            chunks_done: 0,
            corpus_version: 1,
            error: 'Aucun texte extrait du PDF (document scanné ou protégé ?).',
            created_at: '2026-08-01T10:00:00Z',
            indexed_at: null,
            progress: 0,
          },
        ],
        total_chunks: 0,
        embedding_model: 'intfloat/multilingual-e5-small',
        is_ingesting: false,
      });
    await fixture.whenStable();

    expect(text(fixture)).toContain('Échec');
    expect(text(fixture)).toContain('Aucun texte extrait');
  });

  it('EvaluationPage renders the ablation and the decision taken from it', async () => {
    const fixture = await mount(EvaluationPage);

    TestBed.inject(HttpTestingController)
      .expectOne('/api/evaluation')
      .flush({
        model: 'intfloat/multilingual-e5-small',
        corpus_chunks: 712,
        best_arm: 'weighted w=0.0',
        deployed_weight_bm25: 0.0,
        arms: [
          {
            name: 'weighted w=0.0',
            arm: 'dense',
            hit_at_1: 0.679,
            hit_at_3: 0.786,
            hit_at_5: 0.839,
            hit_at_10: 0.875,
            mrr: 0.747,
            ndcg_at_10: 0.778,
          },
          {
            name: 'weighted w=1.0',
            arm: 'lexical',
            hit_at_1: 0.179,
            hit_at_3: 0.286,
            hit_at_5: 0.357,
            hit_at_10: 0.554,
            mrr: 0.265,
            ndcg_at_10: 0.332,
          },
        ],
        golden_set: {
          questions: 56,
          sources: ['penal_code.pdf'],
          one_question_worth: 0.0179,
        },
        encoder_fix: {
          before_model: 'paraphrase-multilingual-MiniLM-L12-v2',
          before_max_tokens: 128,
          before_hit_at_1: 0.25,
          before_hit_at_5: 0.5,
          before_mrr: 0.364,
          after_model: 'intfloat/multilingual-e5-small',
          after_max_tokens: 512,
          after_hit_at_1: 0.679,
          after_hit_at_5: 0.839,
          after_mrr: 0.747,
          truncated_chunks: 277,
          total_chunks: 712,
          dropped_token_pct: 11.3,
        },
      });
    await fixture.whenStable();

    const body = text(fixture);
    // The measurement...
    expect(body).toContain('0.839');
    expect(body).toContain('56');
    // ...and the decision taken from it, which is the point of the page.
    expect(body).toContain('déployé');
    expect(body).toContain('tronquait');
  });
});
