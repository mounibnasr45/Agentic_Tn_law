import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE } from './api-base';
import { CorpusDocument } from './api.types';

/**
 * The source PDFs the agent cites.
 *
 * WHY THE FILE IS FETCHED AS A BLOB RATHER THAN POINTED AT WITH <iframe src>. The obvious
 * implementation — `<iframe [src]="/api/documents/{id}/file">` — cannot work here: the
 * browser issues that request itself, with no way to attach an Authorization header, so
 * it arrives unauthenticated and gets a 401. Pulling the bytes through HttpClient keeps
 * authInterceptor and the single-flight refresh in play, and the resulting object URL is
 * what the iframe actually renders. The files are ~150-500KB, so holding one in memory is
 * not a concern; the caller is responsible for revoking the URL (see the page component).
 */
@Injectable({ providedIn: 'root' })
export class DocumentsApi {
  private readonly http = inject(HttpClient);

  list(): Observable<CorpusDocument[]> {
    return this.http.get<CorpusDocument[]>(`${API_BASE}/documents`);
  }

  /**
   * `download` only changes the Content-Disposition the server sends. It is irrelevant to
   * the blob itself — both variants return identical bytes — but it is what makes a saved
   * file arrive with the right name, so the download path asks for it.
   */
  file(id: string, download = false): Observable<Blob> {
    const query = download ? '?download=true' : '';
    return this.http.get(`${API_BASE}/documents/${id}/file${query}`, {
      responseType: 'blob',
    });
  }
}
