# syntax=docker/dockerfile:1
# ClaimTrace web image for local development: runs the Next.js dev server with
# hot reload. A production target (next build + standalone output) is deferred
# until deployment work begins.
FROM node:22-alpine

ENV NODE_ENV=development \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

# Dependency layer.
COPY package.json package-lock.json ./
RUN npm ci

# Application sources. The compose bind mount shadows these during development;
# they are copied so the image is usable on its own.
COPY . .

# node:alpine ships a non-root "node" user (uid 1000).
RUN chown -R node:node /app
USER node

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD wget --quiet --spider http://127.0.0.1:3000/ || exit 1

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
