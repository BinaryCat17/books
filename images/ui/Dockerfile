FROM node:22-alpine AS build
WORKDIR /ui
COPY images/ui/package.json images/ui/package-lock.json ./
RUN npm ci
COPY images/ui/ ./
RUN npm run build

FROM caddy:2
COPY images/ui/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /ui/dist /srv
