import { HttpClient, HttpEvent, HttpEventType, HttpRequest } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { API_BASE } from './api-base';
import { AdminUser, CorpusStatus, UploadAccepted } from './api.types';

/** What the upload stream emits: bytes on the wire, then the server's answer. */
export type UploadProgress =
  | { kind: 'sending'; percent: number }
  | { kind: 'accepted'; body: UploadAccepted };

@Injectable({ providedIn: 'root' })
export class AdminApi {
  private readonly http = inject(HttpClient);

  /**
   * Upload a PDF for indexing.
   *
   * TWO DIFFERENT PROGRESS SIGNALS LIVE IN THIS FLOW, and conflating them is the easy
   * mistake. This one — HttpEventType.UploadProgress — is bytes leaving the browser, and
   * it finishes the moment the server has the file. Indexing has not started yet.
   *
   * The one that matters to a user watching a 700-chunk legal code get embedded is
   * chunks_done/chunks_total on the document row, which arrives by polling corpus() after
   * this completes. The server returns 202 Accepted precisely because the work outlives
   * the request.
   */
  upload(file: File): Observable<UploadProgress> {
    const form = new FormData();
    form.append('file', file, file.name);

    const request = new HttpRequest('POST', `${API_BASE}/admin/documents`, form, {
      reportProgress: true,
    });

    return this.http.request<UploadAccepted>(request).pipe(
      map((event: HttpEvent<UploadAccepted>): UploadProgress => {
        if (event.type === HttpEventType.UploadProgress) {
          // event.total is undefined when the server sends no Content-Length back for the
          // request body; report 0 rather than NaN, which would render as "NaN%".
          const percent = event.total ? Math.round((100 * event.loaded) / event.total) : 0;
          return { kind: 'sending', percent };
        }

        if (event.type === HttpEventType.Response) {
          return { kind: 'accepted', body: event.body as UploadAccepted };
        }

        return { kind: 'sending', percent: 0 };
      }),
    );
  }

  /** Every document plus corpus totals. Cheap by design — the admin screen polls it. */
  corpus(): Observable<CorpusStatus> {
    return this.http.get<CorpusStatus>(`${API_BASE}/admin/corpus`);
  }

  /** Every account, with real message and session counts — not a poll target, loaded once. */
  users(): Observable<AdminUser[]> {
    return this.http.get<AdminUser[]>(`${API_BASE}/admin/users`);
  }

  /**
   * Grant or revoke administrator privileges.
   *
   * Returns the updated row rather than void: the server also recomputes message_count
   * and session_count for it, and re-fetching the whole list just to refresh one row's
   * numbers would be wasteful.
   */
  setAdmin(userId: string, isAdmin: boolean): Observable<AdminUser> {
    return this.http.patch<AdminUser>(`${API_BASE}/admin/users/${userId}`, {
      is_admin: isAdmin,
    });
  }
}
