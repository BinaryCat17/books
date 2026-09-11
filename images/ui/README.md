# ui

The browser application, served with the API behind one proxy: a library
(books, runs, jobs with live progress), a viewer (the page with its boxes,
each block's detail and crop, the pairs against truth, metrics per page and
per book), and an admin panel (the registry, users, placements, the ledger).

Vite, React and TypeScript over a hand-typed client of the backend's API
(`src/api.ts`, `src/types.ts`; the contract is `schema/openapi/backend.json`
and the schemas). Develop: `npm ci && npm run dev` against a stack on
`:8080` (or `VITE_API`). Check: `npm run build`. The image builds the app
and serves it with Caddy, `/api` proxied to the backend. `check.mjs` drives
the app in a browser over a running stack (log in, open a run, measure a
page, the admin panel) and screenshots each screen.
