import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE } from './api-base';
import { AskRequest, AskResponse, ConversationSummary, MessageResponse } from './api.types';

@Injectable({ providedIn: 'root' })
export class ChatApi {
  private readonly http = inject(HttpClient);

  /**
   * Runs the agent. This is the slow one — retrieval plus an LLM round trip — so callers
   * must show a pending state, and nginx needs `proxy_read_timeout` well above its 60s
   * default or a slow answer is turned into a 504.
   */
  ask(question: string, conversationId: string | null): Observable<AskResponse> {
    const body: AskRequest = { question, conversation_id: conversationId };
    return this.http.post<AskResponse>(`${API_BASE}/ask`, body);
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
