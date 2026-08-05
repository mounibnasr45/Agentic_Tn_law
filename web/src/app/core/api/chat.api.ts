import { HttpClient, HttpDownloadProgressEvent, HttpEventType } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { I18nService } from '../i18n/i18n.service';
import { API_BASE } from './api-base';
import {
  AskRequest,
  AskResponse,
  ChatStreamEvent,
  ConversationSummary,
  MessageResponse,
} from './api.types';

@Injectable({ providedIn: 'root' })
export class ChatApi {
  private readonly http = inject(HttpClient);
  // The agent answers in whichever language the UI is showing — an English
  // interface replying in French would be a worse experience than either alone.
  private readonly i18n = inject(I18nService);

  /**
   * Runs the agent. This is the slow one — retrieval plus an LLM round trip — so callers
   * must show a pending state, and nginx needs `proxy_read_timeout` well above its 60s
   * default or a slow answer is turned into a 504.
   */
  ask(question: string, conversationId: string | null): Observable<AskResponse> {
    const body: AskRequest = {
      question,
      conversation_id: conversationId,
      language: this.i18n.current(),
    };
    return this.http.post<AskResponse>(`${API_BASE}/ask`, body);
  }

  /**
   * Same call as ask(), but each trace step arrives the instant the agent records it
   * instead of all at once at the end — see POST /api/ask/stream.
   *
   * WHY HttpClient AND NOT A RAW fetch(). `observe: 'events'` + `reportProgress: true` +
   * `responseType: 'text'` makes the XHR backend emit an HttpDownloadProgressEvent on every
   * chunk the server flushes, and — critically — `partialText` holds EVERYTHING received so
   * far, not just the new bytes. Going through HttpClient rather than fetch() directly means
   * authInterceptor and refreshInterceptor still run: the Authorization header and the
   * single-flight 401 refresh-and-retry (see refresh.interceptor.ts) come for free instead
   * of needing a second implementation for this one endpoint. It also means this stays
   * testable with the same HttpTestingController the rest of the app's tests already use —
   * a TestRequest can `.event()` synthetic DownloadProgress ticks.
   */
  askStream(question: string, conversationId: string | null): Observable<ChatStreamEvent> {
    const body: AskRequest = {
      question,
      conversation_id: conversationId,
      language: this.i18n.current(),
    };

    return new Observable<ChatStreamEvent>((subscriber) => {
      // `consumed` is how much of `partialText` has already been parsed into lines — each
      // progress tick repeats everything from byte 0, so re-scanning it all every time
      // would re-emit every earlier line on every tick.
      let consumed = 0;
      let buffer = '';

      const subscription = this.http
        .post(`${API_BASE}/ask/stream`, body, {
          observe: 'events',
          reportProgress: true,
          responseType: 'text',
        })
        .subscribe({
          next: (event) => {
            if (event.type !== HttpEventType.DownloadProgress) {
              return;
            }
            const received = (event as HttpDownloadProgressEvent).partialText ?? '';
            buffer += received.slice(consumed);
            consumed = received.length;

            const lines = buffer.split('\n');
            buffer = lines.pop() ?? ''; // the last, possibly incomplete, line

            for (const line of lines) {
              if (line.trim().length === 0) {
                continue;
              }
              subscriber.next(JSON.parse(line) as ChatStreamEvent);
            }
          },
          error: (error: unknown) => subscriber.error(error),
          complete: () => subscriber.complete(),
        });

      return () => subscription.unsubscribe();
    });
  }

  /** Scoped to the authenticated user by the backend; there is no "all conversations". */
  listConversations(): Observable<ConversationSummary[]> {
    return this.http.get<ConversationSummary[]>(`${API_BASE}/conversations`);
  }

  /** 404 both when it does not exist and when it belongs to someone else — by design. */
  history(conversationId: string): Observable<MessageResponse[]> {
    return this.http.get<MessageResponse[]>(`${API_BASE}/conversations/${conversationId}`);
  }
}
