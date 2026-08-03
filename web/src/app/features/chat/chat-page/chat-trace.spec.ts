import {
  HttpDownloadProgressEvent,
  HttpEventType,
  provideHttpClient,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { ChatPage } from './chat-page';

/**
 * Does the trace panel actually render when the API returns a trace?
 *
 * Written because the panel did not appear in the browser while every layer checked out
 * individually: the backend returned a populated trace, the served bundle contained the
 * panel's markup in the same chunk as the chat page, and the session was healthy. That
 * combination means the bug is either in the wiring between them — or nowhere, and the
 * browser was stale. This test settles which.
 */
const TRACE_RESPONSE = {
  conversation_id: 'c0ffee00-0000-4000-8000-000000000001',
  answer: "Selon l'article 264, la peine est de cinq ans.",
  citations: [
    {
      chunk_id: 1,
      source: 'penal_code.pdf',
      article_number: 'Article 264',
      score: 0.812,
      rank: 1,
      excerpt: 'La peine est de cinq ans...',
    },
  ],
  trace: {
    steps: [
      {
        kind: 'retrieval',
        label: 'Recherche dans le corpus',
        query: 'peine vol simple',
        results: [
          { article_number: 'Article 264', score: 0.812, rank: 1 },
          { article_number: 'Article 259', score: 0.809, rank: 2 },
        ],
        detail: null,
      },
      {
        kind: 'reflection',
        label: 'Relecture du brouillon',
        query: null,
        results: [],
        detail: 'Terme(s) employé(s) sans définition dans les extraits : tentative',
      },
    ],
    iterations_used: 2,
    max_iterations: 4,
    regrounded: true,
  },
};

async function mountChat(routed = false): Promise<ComponentFixture<ChatPage>> {
  await TestBed.configureTestingModule({
    imports: [ChatPage],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      // `routed` wires the REAL route with input binding. Without it, the
      // router.navigate(['/chat', id]) that send() performs on a NEW conversation is a
      // no-op, the conversationId input never changes, and the route effect never runs —
      // so a plain provideRouter([]) silently skips the exact path where a freshly
      // received trace could be overwritten by reloaded history.
      routed
        ? provideRouter(
            [{ path: 'chat/:conversationId', component: ChatPage }],
            withComponentInputBinding(),
          )
        : provideRouter([]),
    ],
  }).compileComponents();

  const fixture = TestBed.createComponent(ChatPage);
  await fixture.whenStable();
  return fixture;
}

function text(fixture: ComponentFixture<unknown>): string {
  return (fixture.nativeElement as HTMLElement).textContent ?? '';
}

/**
 * askStream() (see chat.api.ts) only reacts to DownloadProgress events and reads the
 * complete-so-far body from `partialText` — it ignores the terminal Response event flush()
 * normally sends. So a single event carrying the full NDJSON body, one line per item, stands
 * in for however many chunks the real server would have flushed.
 */
function flushStream(httpMock: HttpTestingController, url: string, events: unknown[]): void {
  const ndjson = events.map((event) => JSON.stringify(event)).join('\n') + '\n';
  const req = httpMock.expectOne(url);
  req.event({
    type: HttpEventType.DownloadProgress,
    loaded: ndjson.length,
    total: ndjson.length,
    partialText: ndjson,
  } as HttpDownloadProgressEvent);
  req.flush(ndjson);
}

describe('chat page — agent trace rendering', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it('renders the trace panel when /api/ask returns a trace', async () => {
    const fixture = await mountChat();
    const httpMock = TestBed.inject(HttpTestingController);

    // The sidebar loads on construction; drain it so the ask request is unambiguous.
    httpMock.expectOne('/api/conversations').flush([]);
    await fixture.whenStable();

    // Drive the real send() path, exactly as the suggestion buttons do.
    (fixture.componentInstance as unknown as { send(q: string): void }).send(
      'Quelle est la peine pour vol simple ?',
    );
    await fixture.whenStable();

    flushStream(httpMock, '/api/ask/stream', [{ event: 'final', data: TRACE_RESPONSE }]);
    await fixture.whenStable();

    const body = text(fixture);

    // The answer arrives — proving the response was consumed at all.
    expect(body).toContain('article 264');

    // The panel itself.
    expect(body).toContain("Raisonnement de l'agent");
    // The agent's OWN query, which is the panel's whole point.
    expect(body).toContain('peine vol simple');
    // The bounded loop.
    expect(body).toContain('2 / 4');
    // The reflection step's finding.
    expect(body).toContain('tentative');
    // The regrounded badge.
    expect(body).toContain('réancrée');
  });

  it('renders the "no source consulted" state for a response with an empty trace', async () => {
    const fixture = await mountChat();
    const httpMock = TestBed.inject(HttpTestingController);

    httpMock.expectOne('/api/conversations').flush([]);
    await fixture.whenStable();

    (fixture.componentInstance as unknown as { send(q: string): void }).send('Bonjour ?');
    await fixture.whenStable();

    flushStream(httpMock, '/api/ask/stream', [
      {
        event: 'final',
        data: {
          ...TRACE_RESPONSE,
          trace: { steps: [], iterations_used: 0, max_iterations: 4, regrounded: false },
        },
      },
    ]);
    await fixture.whenStable();

    // An empty step list still renders the panel, but with the explicit "no source
    // consulted" state rather than a silently empty box.
    expect(text(fixture)).toContain("Raisonnement de l'agent");
    expect(text(fixture)).toContain("n'a interrogé aucune source");
  });

  it('keeps the trace after send() navigates to the new conversation URL', async () => {
    // THE PATH A REAL USER TAKES: the empty state's suggestion buttons start a NEW
    // conversation, so send() navigates to /chat/{id} once the answer arrives.
    //
    // RouterTestingHarness, not TestBed.createComponent: the component must live inside a
    // real router outlet for withComponentInputBinding to feed the route param into the
    // conversationId input. Created detached, that input stays undefined forever, the route
    // effect sees id=null while loadedId holds the new UUID, and messages.set([]) wipes the
    // conversation — a harness artefact that looks exactly like the bug being hunted.
    const { RouterTestingHarness } = await import('@angular/router/testing');

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter(
          [
            { path: 'chat', component: ChatPage },
            { path: 'chat/:conversationId', component: ChatPage },
          ],
          withComponentInputBinding(),
        ),
      ],
    });

    const harness = await RouterTestingHarness.create('/chat');
    const httpMock = TestBed.inject(HttpTestingController);

    httpMock.expectOne('/api/conversations').flush([]);
    await harness.fixture.whenStable();

    const page = harness.routeDebugElement!.componentInstance as unknown as {
      send(q: string): void;
    };
    page.send('Quelles sont les circonstances aggravantes du vol ?');
    await harness.fixture.whenStable();

    flushStream(httpMock, '/api/ask/stream', [{ event: 'final', data: TRACE_RESPONSE }]);
    await harness.fixture.whenStable();

    // send() navigates itself; give the router a beat, then answer any history refetch the
    // way the real endpoint would (no citations, no trace) so a wipe would be visible.
    await harness.fixture.whenStable();
    for (const r of httpMock.match(
      `/api/conversations/${TRACE_RESPONSE.conversation_id}`,
    )) {
      r.flush([
        {
          role: 'assistant',
          content: TRACE_RESPONSE.answer,
          latency_ms: 14658,
          created_at: new Date().toISOString(),
        },
      ]);
    }
    await harness.fixture.whenStable();

    const body = (harness.fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(body).toContain("Raisonnement de l'agent");
    expect(body).toContain('source citée');
  });
});
