import { ChangeDetectionStrategy, Component, inject, input, output } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { CONSTRAINTS } from '../../../core/api/api.types';
import { I18nService } from '../../../core/i18n/i18n.service';

@Component({
  selector: 'app-message-composer',
  imports: [
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <form class="composer" [formGroup]="form" (ngSubmit)="submit()">
      <!--
        hideRequiredMarker: Material appends "*" to the label of a required control. On a
        single-field composer whose only purpose is to be filled in, that asterisk is pure
        noise — it was rendering as "Posez votre question juridique…*".
      -->
      <mat-form-field
        appearance="outline"
        class="composer-field"
        subscriptSizing="dynamic"
        hideRequiredMarker
      >
        <mat-label>{{ t.s().composerPlaceholder }}</mat-label>
        <textarea
          matInput
          formControlName="question"
          rows="2"
          [attr.maxlength]="rules.maxLength"
          (keydown)="onKeydown($event)"
        ></textarea>
        <mat-hint>{{ t.s().composerHint }}</mat-hint>
        <mat-hint align="end">
          {{ form.controls.question.value.length }} / {{ rules.maxLength }}
        </mat-hint>
      </mat-form-field>

      <button
        matButton="filled"
        type="submit"
        class="composer-send"
        [disabled]="form.invalid || disabled()"
      >
        <mat-icon>send</mat-icon>
        <span class="send-label">{{ t.s().send }}</span>
      </button>
    </form>
  `,
  styles: `
    .composer {
      display: flex;
      gap: 0.75rem;
      align-items: flex-start;
    }
    .composer-field {
      flex: 1 1 auto;
    }
    .composer-send {
      margin-top: 0.5rem;
      flex: 0 0 auto;
    }
    @media (max-width: 640px) {
      .send-label {
        display: none;
      }
    }
  `,
})
export class MessageComposer {
  protected readonly t = inject(I18nService);

  private readonly fb = inject(FormBuilder);

  readonly disabled = input(false);
  readonly questionSubmitted = output<string>();

  protected readonly rules = CONSTRAINTS.question;

  protected readonly form = this.fb.nonNullable.group({
    question: [
      '',
      [
        Validators.required,
        Validators.minLength(CONSTRAINTS.question.minLength),
        Validators.maxLength(CONSTRAINTS.question.maxLength),
      ],
    ],
  });

  /**
   * Enter sends; Shift+Enter inserts a newline.
   *
   * Checked manually rather than with Angular's `(keydown.enter)` binding, because that
   * binding's modifier matching is easy to get subtly wrong — and a composer that submits
   * a half-typed question every time the user tries to start a new line is infuriating.
   */
  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.submit();
    }
  }

  protected submit(): void {
    if (this.form.invalid || this.disabled()) {
      return;
    }
    this.questionSubmitted.emit(this.form.controls.question.value.trim());
    this.form.reset({ question: '' });
  }
}
