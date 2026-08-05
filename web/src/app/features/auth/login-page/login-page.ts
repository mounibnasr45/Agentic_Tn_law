import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router } from '@angular/router';
import { CONSTRAINTS } from '../../../core/api/api.types';
import { AuthService } from '../../../core/auth/auth.service';
import { I18nService } from '../../../core/i18n/i18n.service';

type Mode = 'login' | 'register';

@Component({
  selector: 'app-login-page',
  imports: [
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatProgressBarModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './login-page.html',
  styleUrl: './login-page.scss',
})
export class LoginPage {
  protected readonly t = inject(I18nService);

  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly passwordRules = CONSTRAINTS.password;
  protected readonly pending = signal(false);

  // Bound from the route's `data.mode` (see app.routes.ts's /register entry) via
  // withComponentInputBinding, so the landing page's "Sign up" button can link straight
  // into registration instead of the visitor having to land on the login form and find
  // the toggle themselves. Named `mode` (not aliased) because Angular's style guide
  // forbids renaming an input — which is exactly why the form's own reactive state below
  // is `formMode`, not `mode`: the input owns that name, this is only ever read once, at
  // construction.
  readonly mode = input<Mode>('login');

  protected readonly formMode = signal<Mode>('login');

  protected readonly submitLabel = computed(() =>
    this.formMode() === 'login' ? this.t.s().signIn : this.t.s().signUp,
  );

  /**
   * `nonNullable` makes these `FormControl<string>` rather than `FormControl<string | null>`,
   * so nothing downstream has to null-check a text input that cannot be null.
   */
  protected readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.maxLength(CONSTRAINTS.password.maxLength)]],
  });

  constructor() {
    // Seeds the form's own state from the route once, at construction — applyMode still
    // goes through the same validator-switching logic toggleMode uses, so a visitor who
    // arrives via /register and then clicks "already have an account?" gets exactly the
    // same form the login page always had.
    this.applyMode(this.mode());
  }

  /**
   * The 12-character minimum applies to REGISTRATION only.
   *
   * `RegisterRequest` enforces it (app/api/schemas/auth.py) but `LoginRequest` deliberately
   * accepts `min_length=1`. Enforcing 12 on the login form too would lock out any account
   * whose password predates the rule — the client refusing to send a credential the server
   * would have happily accepted.
   */
  private applyMode(next: Mode): void {
    this.formMode.set(next);

    const password = this.form.controls.password;
    password.setValidators(
      next === 'register'
        ? [
            Validators.required,
            Validators.minLength(CONSTRAINTS.password.minLength),
            Validators.maxLength(CONSTRAINTS.password.maxLength),
          ]
        : [Validators.required, Validators.maxLength(CONSTRAINTS.password.maxLength)],
    );
    password.updateValueAndValidity();
  }

  protected toggleMode(): void {
    this.applyMode(this.formMode() === 'login' ? 'register' : 'login');
  }

  protected submit(): void {
    if (this.form.invalid || this.pending()) {
      return;
    }
    this.pending.set(true);

    const credentials = this.form.getRawValue();
    const request =
      this.formMode() === 'login'
        ? this.auth.login(credentials)
        : this.auth.register(credentials);

    request.subscribe({
      next: () => {
        void this.router.navigate(['/chat']);
      },
      error: () => {
        // The message is already on screen: httpErrorInterceptor renders the server's own
        // detail ("Cette adresse email est déjà utilisée.", "Email ou mot de passe
        // incorrect.") which is more precise than anything this component could guess.
        this.pending.set(false);
      },
    });
  }
}
