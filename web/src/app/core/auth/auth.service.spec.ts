import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { TokenPair } from '../api/api.types';
import { AuthService } from './auth.service';
import { AuthStore } from './auth.store';
import { TokenStorage } from './token.storage';

function pair(suffix: string): TokenPair {
  return {
    access_token: `access-${suffix}`,
    refresh_token: `refresh-${suffix}`,
    token_type: 'bearer',
    expires_in: 900,
  };
}

/**
 * These tests exist for one reason: the obvious refresh implementation destroys the user's
 * session, and NO single-request test can detect it.
 *
 * The backend revokes a refresh token on use and treats a second presentation of the same
 * token as a replay attack, revoking the entire chain. So the moment two requests 401 at
 * once — which is the normal case on page load — a client that refreshes per-request logs
 * the user out. The first test below is the regression guard for exactly that.
 */
describe('AuthService.refreshOnce (single-flight)', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;
  let storage: TokenStorage;

  beforeEach(() => {
    localStorage.clear();

    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });

    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
    storage = TestBed.inject(TokenStorage);

    storage.save(pair('1'));
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('issues EXACTLY ONE http request for three concurrent callers', () => {
    const received: TokenPair[] = [];

    // Three requests 401 simultaneously — /auth/me, /conversations and /health on page load.
    service.refreshOnce().subscribe((tokens) => received.push(tokens));
    service.refreshOnce().subscribe((tokens) => received.push(tokens));
    service.refreshOnce().subscribe((tokens) => received.push(tokens));

    // THE assertion. expectOne fails if there were zero requests OR more than one, so a
    // regression that reintroduces per-request refreshing turns this red immediately.
    const request = httpMock.expectOne('/api/auth/refresh');
    expect(request.request.body).toEqual({ refresh_token: 'refresh-1' });

    request.flush(pair('2'));

    // All three callers got the result of that single call.
    expect(received).toHaveLength(3);
    expect(received.every((tokens) => tokens.access_token === 'access-2')).toBe(true);
    expect(storage.accessToken()).toBe('access-2');
    expect(storage.refreshToken()).toBe('refresh-2');
  });

  it('permits a NEW refresh once the first has settled', () => {
    service.refreshOnce().subscribe();
    httpMock.expectOne('/api/auth/refresh').flush(pair('2'));

    // Proves `finalize` cleared the cached observable. Without it the session would get
    // exactly one refresh per page load and then silently stop renewing.
    service.refreshOnce().subscribe();
    const second = httpMock.expectOne('/api/auth/refresh');

    // And it presents the ROTATED token, not the revoked original.
    expect(second.request.body).toEqual({ refresh_token: 'refresh-2' });
    second.flush(pair('3'));

    expect(storage.refreshToken()).toBe('refresh-3');
  });

  it('clears the session when the refresh token is rejected', () => {
    const store = TestBed.inject(AuthStore);
    let errored = false;

    service.refreshOnce().subscribe({ error: () => (errored = true) });

    // What the backend returns once a replay has revoked the chain.
    httpMock
      .expectOne('/api/auth/refresh')
      .flush(
        { detail: 'Session révoquée pour raison de sécurité. Veuillez vous reconnecter.' },
        { status: 401, statusText: 'Unauthorized' },
      );

    expect(errored).toBe(true);
    expect(storage.accessToken()).toBeNull();
    expect(storage.refreshToken()).toBeNull();
    expect(store.isAuthenticated()).toBe(false);
  });

  it('does not call the API when there is no refresh token to present', () => {
    storage.clear();
    let errored = false;

    service.refreshOnce().subscribe({ error: () => (errored = true) });

    expect(errored).toBe(true);
    httpMock.expectNone('/api/auth/refresh');
  });
});
