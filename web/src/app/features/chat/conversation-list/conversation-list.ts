import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { ConversationSummary } from '../../../core/api/api.types';
import { I18nService } from '../../../core/i18n/i18n.service';

/**
 * The conversation sidebar. Presentational: it takes a list and renders links.
 *
 * There is deliberately no rename or delete here. `app/api/routes/chat.py` exposes only
 * list and history — offering buttons that cannot work, or hiding a "delete" that merely
 * drops the row from this array, would both be worse than not offering them.
 */
@Component({
  selector: 'app-conversation-list',
  imports: [RouterLink, RouterLinkActive, MatListModule, MatButtonModule, MatIconModule, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="conversations">
      <a matButton="outlined" routerLink="/chat" class="new-conversation">
        <mat-icon>add</mat-icon>
        {{ t.s().newConversation }}
      </a>

      <mat-nav-list>
        @for (conversation of conversations(); track conversation.id) {
          <a
            mat-list-item
            [routerLink]="['/chat', conversation.id]"
            routerLinkActive="active-conversation"
          >
            <span matListItemTitle>{{ conversation.title ?? '(sans titre)' }}</span>
            <span matListItemLine>{{ conversation.updated_at | date: 'short' }}</span>
          </a>
        } @empty {
          <p class="empty">{{ t.s().noConversationsYet }}</p>
        }
      </mat-nav-list>
    </div>
  `,
  styles: `
    .conversations {
      display: flex;
      flex-direction: column;
      height: 100%;
    }
    .new-conversation {
      margin: 1rem;
      flex: 0 0 auto;
    }
    mat-nav-list {
      overflow-y: auto;
      flex: 1 1 auto;
    }
    .active-conversation {
      background-color: color-mix(in srgb, var(--mat-sys-primary) 14%, transparent);
    }
    .empty {
      padding: 0 1rem;
      font: var(--mat-sys-body-small);
      opacity: 0.7;
    }
  `,
})
export class ConversationList {
  protected readonly t = inject(I18nService);

  readonly conversations = input.required<ConversationSummary[]>();
}
