/**
 * Every API call is same-origin and relative.
 *
 * nginx serves this app and proxies `/api` through to FastAPI (see web/nginx.conf.template),
 * so the browser only ever talks to one origin. That removes two whole classes of problem:
 * there is no CORS preflight to configure, and there is no build-time or runtime API host to
 * inject — the same built image works locally under docker compose and on Render.
 *
 * `ng serve` gets the same behaviour from proxy.conf.json during development.
 */
export const API_BASE = '/api';
