import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';
import { TokenStorage } from './core/auth/token.storage';

describe('App shell', () => {
  beforeEach(async () => {
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
  });

  afterEach(() => localStorage.clear());

  it('creates', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('does not fetch the profile when there is no session', () => {
    TestBed.createComponent(App);

    // A logged-out visitor must not trigger an authenticated call — it would 401, and the
    // error interceptor would greet them with a snackbar on the login screen.
    TestBed.inject(HttpTestingController).expectNone('/api/auth/me');
  });

  it('restores the profile when tokens survived a reload', async () => {
    TestBed.inject(TokenStorage).save({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
      expires_in: 900,
    });

    const fixture = TestBed.createComponent(App);
    const httpMock = TestBed.inject(HttpTestingController);

    // The whole point of persisting tokens: a reload keeps you logged in and the profile is
    // re-fetched, rather than the user being bounced to /login.
    httpMock.expectOne('/api/auth/me').flush({ id: 'u-1', email: 'mounib@example.tn' });
    await fixture.whenStable();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('mounib@example.tn');
    httpMock.verify();
  });
});
