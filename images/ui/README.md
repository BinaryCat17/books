# ui

The browser application, served with the API behind one proxy: a library
(books, runs, jobs with live progress), a viewer (the page with its boxes,
each block's detail and crop, a correction of any block landing in the
derived run, exports as html, markdown or text, the pairs against truth,
metrics per page and per book; for admins a label mode that starts a
truth, draws and relabels its boxes, orders them and saves a layer), and an
admin panel (the registry, users, placements, the ledger).

Vite, React and TypeScript over a hand-typed client of the backend's API
(`src/api.ts`, `src/types.ts`; the contract is `schema/openapi/backend.json`
and the schemas). Develop: `npm ci && npm run dev` against a stack on
`:8080` (`API=http://host:port npm run dev` for another). Check:
`npm run build` (types and bundle) and `npm test` (the client's error
mapping, the verdict logic, the labeler's edits, a correction's diff). The image builds the app and serves it
with Caddy, `/api` proxied to the backend. `npm run browser` drives the
app in Chromium over a running stack (log in, open a run, measure a page,
export it, correct a block, label a page, the admin panel) and screenshots each screen; it needs the `playwright`
package, which is not a dependency, or the `mcr.microsoft.com/playwright`
image.
