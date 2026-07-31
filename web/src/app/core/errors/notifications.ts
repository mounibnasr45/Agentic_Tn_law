import { Injectable, inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

/**
 * One place that decides how a message is shown. Wrapping MatSnackBar rather than injecting
 * it directly means the interceptor can be tested by asserting on a spy, with no Material
 * overlay in the test.
 */
@Injectable({ providedIn: 'root' })
export class Notifications {
  private readonly snackBar = inject(MatSnackBar);

  /** Errors stay until dismissed — an auto-hiding legal error is one the user never read. */
  error(message: string): void {
    this.snackBar.open(message, 'Fermer', { panelClass: 'snack-error' });
  }

  info(message: string): void {
    this.snackBar.open(message, 'Fermer', { duration: 4000 });
  }
}
