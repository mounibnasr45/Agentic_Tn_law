# Angular, explained against this codebase

A primer for someone who knows Python and FastAPI well and has not written Angular. Every
example is code we are actually about to write for the Tunisian legal agent — not a todo
list. Read this once and the files in `web/` will be recognisable when they land.

Angular version: **22** (current stable, June 2026). Everything here uses the modern API
surface — standalone components, signals, `inject()`. If you find a tutorial online full of
`@NgModule`, `constructor(private http: HttpClient)` and `*ngIf`, it predates 2023 and is
teaching you a dialect we are not writing.

Three facts about our specific setup, because they change what correct code looks like:

- **The app is zoneless.** There is no `zone.js` in `web/package.json` — Angular 22 scaffolds
  this way now. See section 7; it is the single most important thing on this page.
- **Components have no `.component` suffix.** The v20+ style guide names a component file
  after what it contains: `citation-card.ts` exporting `class CitationCard`. `ng generate`
  does this for you. Services and stores keep a readable role in the name (`auth.store.ts`,
  `chat.api.ts`), and guards/interceptors keep theirs because they are plain functions.
- **Tests run on Vitest**, not Karma/Jasmine.

---

## 0. The mental model shift from Streamlit

Streamlit reruns your entire script top-to-bottom on every interaction. State survives only
because you stashed it in `st.session_state`, and the UI is a side effect of execution
order.

Angular is the opposite. You **declare** a component tree once; it stays mounted. State
lives in objects that outlive any single render, and the framework re-renders only the parts
whose inputs changed. Nothing "reruns".

That difference is why the citation panel in Streamlit collapses every time you send a
message, and why it won't in Angular.

---

## 1. Components — the unit of UI

A component is a class plus a template. This is the real one that renders a single citation
returned by `/api/ask`:

```ts
// web/src/app/features/chat/citation-card/citation-card.ts
import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { MatExpansionModule } from '@angular/material/expansion';
import { Citation } from '../../../core/api/api.types';

@Component({
  selector: 'app-citation-card',
  // DecimalPipe is imported because the template uses `| number`. Miss it and the
  // template fails to compile — pipes are dependencies like anything else.
  imports: [MatExpansionModule, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-expansion-panel>
      <mat-expansion-panel-header>
        <mat-panel-title>
          📖 {{ citation().article_number ?? 'Préambule' }}
        </mat-panel-title>
        <mat-panel-description>
          {{ citation().source }} · {{ citation().score | number: '1.3-3' }}
        </mat-panel-description>
      </mat-expansion-panel-header>
      <p>{{ citation().excerpt }}</p>
    </mat-expansion-panel>
  `,
})
export class CitationCard {
  readonly citation = input.required<Citation>();
}
```

Things to notice:

- **`selector`** is the HTML tag you write to use it: `<app-citation-card [citation]="c" />`.
- **`imports`** — a component declares its own dependencies. There is no global registry.
  If you use `@if` you need nothing; if you use Material's expansion panel you import
  `MatExpansionModule` here. Forget it and the template fails to compile, loudly.
- **`input.required<Citation>()`** is the modern replacement for `@Input()`. It returns a
  *signal* (section 2), so you read it as `citation()` — with parentheses — in the template.
  `required` means Angular refuses to compile a usage that doesn't pass it.
- **`{{ }}`** is interpolation, and `| number: '1.3-3'` is a *pipe* — a display-time
  formatter, here forcing 3 decimal places on the retrieval score.
- **`OnPush`** — see section 7.

### Control flow

Angular has its own template syntax for conditionals and loops:

```html
@if (messages().length === 0) {
  <p>Posez votre première question.</p>
} @else {
  @for (message of messages(); track message.id) {
    <app-message [message]="message" />
  } @empty {
    <p>Aucun message.</p>
  }
}
```

`track` is **mandatory** in `@for`, and it matters: it tells Angular how to identify a row
across re-renders. Track by an unstable value and the framework destroys and rebuilds every
DOM node on each update — which, in a chat log, means losing scroll position and collapsing
every open citation panel.

---

## 2. Signals — how state works

A signal is a value that knows who is reading it. Change it, and exactly those readers
update. This is Angular's core state primitive since v16 and the thing that makes the
framework comprehensible.

```ts
import { computed, signal } from '@angular/core';

const chunks = signal(0);                             // create
chunks();                                             // read  -> 0
chunks.set(712);                                      // write
chunks.update((n) => n + 1);                          // write from previous

const corpusReady = computed(() => chunks() > 0);     // derived, cached, auto-updating
```

`computed()` re-evaluates only when something it read has actually changed, and only when
someone asks for its value. You never wire up subscriptions or invalidation by hand.

Here is `AuthStore`, the piece of state the whole app hangs off:

```ts
// web/src/app/core/auth/auth.store.ts
@Injectable({ providedIn: 'root' })
export class AuthStore {
  private readonly _user = signal<User | null>(null);

  /** Exposed read-only: components render the user, they don't assign it. */
  readonly user = this._user.asReadonly();
  readonly isAuthenticated = computed(() => this._user() !== null);

  setUser(user: User | null): void {
    this._user.set(user);
  }
}
```

`asReadonly()` is doing real work: a component can call `store.user()` but cannot call
`store.user.set(...)`. Writes go through methods on the store, so there is exactly one place
where the user can change. This is the same instinct as keeping SQLAlchemy writes inside a
repository instead of scattering `session.add()` through your handlers.

`{ providedIn: 'root' }` makes it a singleton for the app's lifetime — the analogue of an
object you build once in FastAPI's `lifespan` and hang on `app.state`.

---

## 3. Dependency injection — `inject()`

You already know this pattern. FastAPI:

```python
async def ask(payload: AskRequest, user: CurrentUser, session: SessionDep) -> AskResponse:
```

The handler declares what it needs; something else decides how to build it. Angular does the
same thing, and for the same reason — in `app/api/deps.py` you noted that `Depends()` is
what lets a test swap `get_current_user` with one line. Identical benefit here.

```ts
// web/src/app/core/api/chat.api.ts
@Injectable({ providedIn: 'root' })
export class ChatApi {
  private readonly http = inject(HttpClient);

  ask(question: string, conversationId: string | null): Observable<AskResponse> {
    return this.http.post<AskResponse>('/api/ask', {
      question,
      conversation_id: conversationId,
    });
  }
}
```

`inject(HttpClient)` asks the injector for the configured `HttpClient`. In a test you
override that provider and `ChatApi` never knows the difference.

Note the URL: **`/api/ask`**, relative and same-origin. nginx serves the app and proxies
`/api` to FastAPI, so there is no host to configure and no CORS preflight. That is why
`web/nginx.conf.template` exists.

Note also `conversation_id` — snake_case, matching the Pydantic schema byte-for-byte. We
keep wire types exactly as the API sends them and map to camelCase in one place, so a
backend rename becomes a TypeScript error rather than a silent `undefined`.

---

## 4. Routing and guards

Routes map URLs to components. `loadComponent` is a lazy import — that page's JavaScript is
only downloaded when someone actually visits it.

```ts
// web/src/app/app.routes.ts
export const routes: Routes = [
  { path: '', redirectTo: 'chat', pathMatch: 'full' },
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login-page/login-page.component')
      .then((m) => m.LoginPageComponent),
  },
  {
    path: 'chat/:conversationId',
    canActivate: [authGuard],
    loadComponent: () => import('./features/chat/chat-page/chat-page.component')
      .then((m) => m.ChatPageComponent),
  },
];
```

`:conversationId` is a path parameter, readable inside the component — which is what makes
a conversation deep-linkable, something the Streamlit version could never do.

A guard is just a function returning `true`, `false`, or a redirect:

```ts
// web/src/app/core/auth/auth.guard.ts
export const authGuard: CanActivateFn = () => {
  const store = inject(AuthStore);
  const router = inject(Router);

  return store.isAuthenticated() ? true : router.createUrlTree(['/login']);
};
```

**A guard is a UX affordance, not a security boundary.** It stops a logged-out visitor from
seeing an empty chat shell. It protects nothing — anyone can edit the JavaScript. The real
enforcement is `CurrentUser` in `app/api/deps.py`, server-side, which is where it belongs.

---

## 5. HTTP interceptors — and the one genuinely hard problem

An interceptor is middleware for outgoing requests. It receives a request and a `next`
handler, exactly like FastAPI's `@app.middleware("http")` in `app/main.py`.

The easy one — attach the token to every request:

```ts
// web/src/app/core/auth/auth.interceptor.ts
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const token = inject(TokenStorage).accessToken();
  if (!token) return next(req);

  return next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};
```

Requests are immutable, hence `req.clone()`.

### Now the hard one

Your access token lives 15 minutes (`ACCESS_TOKEN_MINUTES`). When it expires, the API
returns 401 and the client is supposed to call `POST /api/auth/refresh` to get a new pair.

Read what your backend does on refresh (`app/services/auth_service.py`):

> Exchange a refresh token for a **NEW pair. The presented token is revoked.**
> Presenting an already-revoked token revokes the user's **entire chain**: we cannot tell a
> client retrying an old request from an attacker replaying a stolen token.

That is correct security design, and it sets a trap for the naive client.

When the chat page loads, it fires three requests at once: `/auth/me`, `/conversations`,
`/health`. If the access token has just expired, **all three come back 401 together.** The
obvious interceptor — "on 401, refresh, then retry" — now calls `/auth/refresh` three times
with the same stored refresh token. The first call succeeds and revokes that token. The
second and third are now presenting a revoked token, which your backend correctly classifies
as replay, and it **destroys the whole session.** The user is thrown to the login screen for
the crime of loading a page.

The fix is **single-flight**: the first 401 starts a refresh, and every other 401 in that
window waits on the *same* in-flight request rather than starting its own.

```ts
// web/src/app/core/auth/refresh.interceptor.ts  (shape, not the final file)
export const refreshInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);

  // Never intercept the auth endpoints themselves, or a failed refresh loops forever.
  if (req.url.includes('/api/auth/')) return next(req);

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401) return throwError(() => error);

      // Every concurrent 401 receives the SAME observable. One network call, N waiters.
      return auth.refreshOnce().pipe(
        switchMap(() => next(req.clone(/* new token */))),
      );
    }),
  );
};
```

…where `refreshOnce()` caches the in-flight request:

```ts
private inFlight: Observable<TokenPair> | null = null;

refreshOnce(): Observable<TokenPair> {
  this.inFlight ??= this.authApi.refresh(this.storage.refreshToken()!).pipe(
    tap((pair) => this.storage.save(pair)),
    finalize(() => (this.inFlight = null)),   // allow the NEXT expiry to refresh again
    shareReplay({ bufferSize: 1, refCount: false }),
  );
  return this.inFlight;
}
```

`shareReplay` is what makes N subscribers share 1 HTTP call. `finalize` clears the cache so
a later expiry can refresh again — omit it and the user gets exactly one refresh per page
load, then silent failure.

This is the most interesting code in the frontend, and it is worth being able to explain in
an interview: **the bug only exists because the backend's replay detection is real, and you
cannot find it without concurrency.** A single-request test passes happily.

---

## 6. Reactive forms — typed, with validation mirroring the backend

```ts
// web/src/app/features/auth/login-page/login-page.component.ts
private readonly fb = inject(FormBuilder);

readonly form = this.fb.nonNullable.group({
  email: ['', [Validators.required, Validators.email]],
  // 12, matching RegisterRequest in app/api/schemas/auth.py. Length dominates entropy.
  password: ['', [Validators.required, Validators.minLength(12)]],
});
```

`nonNullable` gives you `string` instead of `string | null`, so the compiler stops asking
you to null-check a text input. The template binds with `[formGroup]` and shows errors from
`form.controls.password.errors`.

Client validation is **for feedback speed only**. The server validates again — Pydantic's
`Field(min_length=12)` is the rule that counts. Duplicating it here just means the user
learns about it without a round trip.

---

## 7. Zoneless change detection — read this one twice

Historically Angular shipped `zone.js`, a library that monkey-patched every async primitive
in the browser — `setTimeout`, `addEventListener`, `fetch`, `Promise` — so it could notify
the framework that *something* happened and the whole component tree needed re-checking.
It worked, it cost ~100kB, and it re-checked far more than necessary.

**Our app has no `zone.js`.** Angular 22 scaffolds zoneless by default. Change detection is
driven by signals: when a signal a template reads is updated, Angular schedules a re-render
of exactly the components that read it. Nothing else triggers a render.

That is faster and far easier to reason about, and it comes with one sharp edge:

```ts
// ❌ BROKEN in a zoneless app. Compiles. Runs. Never updates the screen.
export class ChatPage {
  messages: Message[] = [];

  send(q: string) {
    this.chatApi.ask(q, null).subscribe((response) => {
      this.messages.push(response.answer);   // plain array, plain property
    });                                       // nothing tells Angular to re-render
  }
}
```

```ts
// ✅ Correct. The signal write IS the notification.
export class ChatPage {
  readonly messages = signal<Message[]>([]);

  send(q: string) {
    this.chatApi.ask(q, null).subscribe((response) => {
      this.messages.update((current) => [...current, response.answer]);
    });
  }
}
```

Under the old zone-based model the broken version happened to work, because zone.js noticed
the HTTP response and re-checked everything. This is why so much Angular code on the
internet mutates plain properties — and why copying it into this app produces a UI that
silently stops updating.

**The rule: anything the template reads must be a signal** (or come through the `async`
pipe, which handles the notification itself). That is not a style preference here; it is a
correctness requirement.

`ChangeDetectionStrategy.OnPush` is still worth declaring — it makes the same guarantee
explicit and keeps the component correct if the app is ever run with zones — but with
signals it is close to redundant. We set it because it costs one line and documents intent.

---

## What you now have

Enough to read every file in `web/`. The pieces map like this:

| Angular | Its counterpart in `app/` |
|---|---|
| `inject()` | `Depends()` in `app/api/deps.py` |
| `{ providedIn: 'root' }` singleton | an object built in `lifespan`, on `app.state` |
| HTTP interceptor | `@app.middleware("http")` in `app/main.py` |
| `api.types.ts` | `app/api/schemas/*.py` |
| `authGuard` | a UX hint; the real check is `CurrentUser` |
| signal | no equivalent — this is the genuinely new idea |

If only one thing sticks: **signals are the state model, and `inject()` is `Depends()`.**
The rest is syntax.
