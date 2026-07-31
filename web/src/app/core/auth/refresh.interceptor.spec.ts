import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TokenPair } from '../api/api.types';
import { authInterceptor } from './auth.interceptor';
import { refreshInterceptor } from './refresh.interceptor';
import { TokenStorage } from './token.storage';

function pair(suffix: string): TokenPair {
  return {
    access_token: `access-${suffix}`,
    refresh_token: `refresh-${suffix}`,
    token_type: 'bearer',
    expires_in: 900,
  };
}

const UNAUTHORIZED = { status: 401, statusText: 'Unauthorized' };

describe('refreshInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let storage: TokenStorage;

  beforeEach(() => {
    localStorage.clear();

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor, refreshInterceptor])),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });

    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    storage = TestBed.inject(TokenStorage);
    storage.save(pair('1'));
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('renews the token once and replays the request', () => {
    let result: unknown = null;
    http.get('/api/conversations').subscribe((value) => (result = value));

    const first = httpMock.expectOne('/api/conversations');
    expect(first.request.headers.get('Authorization')).toBe('Bearer access-1');
    first.flush({ detail: 'Authentification requise.' }, UNAUTHORIZED);

    httpMock.expectOne('/api/auth/refresh').flush(pair('2'));

    // The replay must carry the NEW token. Reusing the expired one would 401 forever.
    const replay = httpMock.expectOne('/api/conversations');
    expect(replay.request.headers.get('Authorization')).toBe('Bearer access-2');
    replay.flush([{ id: 'c-1', title: 'Vol simple', created_at: '', updated_at: '' }]);

    expect(result).toHaveLength(1);
  });

  it('refreshes ONCE when three requests 401 together', () => {
    // Exactly the page-load scenario: three authenticated calls fired concurrently, all
    // holding the same expired access token.
    http.get('/api/auth/me').subscribe({ error: () => undefined });
    http.get('/api/conversations').subscribe({ error: () => undefined });
    http.get('/api/health').subscribe({ error: () => undefined });

    for (const request of httpMock.match(() => true)) {
      request.flush({ detail: 'Authentification requise.' }, UNAUTHORIZED);
    }

    // If this were per-request, three refreshes would go out, the backend would see two
    // replays of a revoked token, and it would revoke the whole session.
    httpMock.expectOne('/api/auth/refresh').flush(pair('2'));

    const replays = httpMock.match(() => true);
    expect(replays).toHaveLength(3);
    for (const replay of replays) {
      expect(replay.request.headers.get('Authorization')).toBe('Bearer access-2');
      replay.flush({});
    }
  });

  it('does not try to refresh a failed login', () => {
    let status = 0;
    http
      .post('/api/auth/login', { email: 'a@b.tn', password: 'wrong-password' })
      .subscribe({ error: (error: { status: number }) => (status = error.status) });

    httpMock
      .expectOne('/api/auth/login')
      .flush({ detail: 'Email ou mot de passe incorrect.' }, UNAUTHORIZED);

    // A 401 here means "wrong password", not "expired token". Refreshing would be nonsense,
    // and the error must reach the login form unchanged.
    httpMock.expectNone('/api/auth/refresh');
    expect(status).toBe(401);
  });

  it('gives up instead of looping when the replayed request also 401s', () => {
    let status = 0;
    http.get('/api/conversations').subscribe({
      error: (error: { status: number }) => (status = error.status),
    });

    httpMock.expectOne('/api/conversations').flush({}, UNAUTHORIZED);
    httpMock.expectOne('/api/auth/refresh').flush(pair('2'));
    httpMock.expectOne('/api/conversations').flush({}, UNAUTHORIZED);

    // The ALREADY_RETRIED context flag stops a second refresh. Without it this recurses
    // until the browser tab dies.
    httpMock.expectNone('/api/auth/refresh');
    expect(status).toBe(401);
  });
});
