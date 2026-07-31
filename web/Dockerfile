# ── build ────────────────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app

# Copied before the source so this layer is cached on every build that does not change
# dependencies — which is almost all of them.
COPY package.json package-lock.json ./

# `npm ci` not `npm install`: it installs exactly the lockfile, fails if package.json and
# the lock have drifted, and never silently upgrades a transitive dependency mid-build.
RUN npm ci

COPY . .
RUN npm run build


# ── serve ────────────────────────────────────────────────────────────────────────────────
FROM nginx:alpine AS serve

# Where the API lives, as seen from INSIDE this container, as host:port (no scheme — the
# template supplies http://). Overridden per environment:
#   docker compose  -> backend:8000                 (the compose service name)
#   Render          -> injected by `fromService: property: hostport`, because Render
#                      assigns the backend's port dynamically through $PORT
ENV API_HOSTPORT=backend:8000

# Restricts envsubst to API_* variables. Without it the nginx entrypoint would also
# substitute $uri, $host and $remote_addr — they are not env vars, so they would be
# replaced with empty strings and try_files would stop working.
ENV NGINX_ENVSUBST_FILTER=^API_

# Anything in /etc/nginx/templates is rendered into /etc/nginx/conf.d at container start by
# the official image's entrypoint. No custom entrypoint needed.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Angular's application builder emits the browser bundle into dist/<project>/browser.
COPY --from=build /app/dist/agentic-tn-law-web/browser /usr/share/nginx/html

EXPOSE 80
