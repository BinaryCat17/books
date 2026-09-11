FROM node:22-alpine AS build
WORKDIR /ui
COPY images/ui/package.json images/ui/package-lock.json ./
RUN npm ci
COPY images/ui/index.html images/ui/tsconfig.json images/ui/vite.config.ts ./
COPY images/ui/src ./src
RUN npm run build

FROM caddy:2
COPY images/ui/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /ui/dist /srv
