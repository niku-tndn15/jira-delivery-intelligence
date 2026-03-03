# =============================================================================
# frontend/Dockerfile
# Build context: frontend/   (set in docker-compose.yml)
#
# Stage 1 — node:20-alpine
#   Installs npm dependencies and runs `vite build`.
#   The output is the optimised static bundle in /app/dist.
#
# Stage 2 — nginx:alpine
#   Copies only the dist folder from Stage 1 (no node_modules in the image).
#   Installs a custom nginx.conf that:
#     • serves the React SPA with client-side routing fallback
#     • reverse-proxies /api/* → http://backend:8000 (Docker internal DNS)
# =============================================================================

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Copy dependency manifests first for layer caching.
# If package.json / package-lock.json haven't changed, npm ci is skipped.
COPY package.json package-lock.json* ./

# Use `npm ci` for a clean, reproducible install (respects package-lock.json)
RUN npm install

# Copy the rest of the source code
COPY . .

# Vite reads VITE_* env vars at build time.
# The API base URL is handled at runtime by Nginx proxy, so no VITE_ vars needed.
RUN npm run build

# ── Stage 2: Serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Remove the default nginx welcome page config
RUN rm /etc/nginx/conf.d/default.conf

# Install our custom Nginx config (SPA fallback + /api proxy)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the built React app from Stage 1
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# nginx:alpine's default CMD starts nginx in the foreground — no override needed
CMD ["nginx", "-g", "daemon off;"]
