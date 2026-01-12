FROM node:20-alpine AS builder

WORKDIR /app

# Build arguments for non-sensitive configuration only
# These get baked into the static build - NEVER put secrets here
ARG VITE_WS_URL=ws://localhost:8080/ws
ARG VITE_BACKEND=langgraph
ARG VITE_APP_NAME=AGORA HAI
ARG VITE_SESSION_TIMEOUT=3600000

# Set as environment variables for build
ENV VITE_WS_URL=$VITE_WS_URL
ENV VITE_BACKEND=$VITE_BACKEND
ENV VITE_APP_NAME=$VITE_APP_NAME
ENV VITE_SESSION_TIMEOUT=$VITE_SESSION_TIMEOUT

RUN npm install -g pnpm

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Use gateway-aware nginx config when available, fall back to default
COPY nginx.gateway.conf /etc/nginx/conf.d/default.conf

# Entrypoint script for runtime environment injection
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]

