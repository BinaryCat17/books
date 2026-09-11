import type { BookRow, Job, JobEvent, LedgerRow, ModelEntry, PageData, Pairs, Placement, Preset, Record_, RunInfo, RunRow, SeriesRow, User } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const r = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });
  const text = await r.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!r.ok) {
    const d = data as { error?: string; detail?: unknown } | null;
    throw new ApiError(r.status, d?.error ?? (d?.detail ? JSON.stringify(d.detail) : r.statusText));
  }
  return data as T;
}

const run = (book: string, kind: string, label: string) => `/books/${book}/runs/${kind}/${encodeURIComponent(label)}`;

export const api = {
  me: () => call<User>("GET", "/me"),
  login: (name: string, password: string) => call<User>("POST", "/login", { name, password }),
  logout: () => call<{ ok: boolean }>("POST", "/logout"),
  books: () => call<BookRow[]>("GET", "/books"),
  upload: (file: File, name: string) => {
    const f = new FormData();
    f.append("file", file);
    return call<{ book: string }>("POST", `/books?name=${encodeURIComponent(name)}`, undefined, f);
  },
  deleteBook: (book: string) => call<{ deleted: string }>("DELETE", `/books/${book}`),
  runs: (book: string) => call<RunRow[]>("GET", `/books/${book}/runs`),
  run: (book: string, kind: string, label: string) => call<RunInfo>("GET", run(book, kind, label)),
  page: (book: string, kind: string, label: string, i: number) => call<PageData>("GET", `${run(book, kind, label)}/pages/${i}`),
  pairs: (book: string, kind: string, label: string, i: number) => call<Pairs>("GET", `${run(book, kind, label)}/pages/${i}/pairs`),
  pageMetrics: (book: string, kind: string, label: string, i: number) => call<Record_[]>("GET", `${run(book, kind, label)}/pages/${i}/metrics`),
  results: (book: string, kind: string, label: string) => call<{ when: number; records: SeriesRow[] }>("GET", `${run(book, kind, label)}/results`),
  series: (book: string, kind: string, label: string) => call<SeriesRow[]>("GET", `${run(book, kind, label)}/series`),
  imageUrl: (book: string, i: number, dpi = 110) => `/api/books/${book}/pages/${i}/image?dpi=${dpi}`,
  cropUrl: (book: string, kind: string, label: string, anchor: string) => `/api${run(book, kind, label)}/crops/${anchor}`,
  documentUrl: (book: string, kind: string, label: string) => `/api${run(book, kind, label)}/document`,
  jobs: () => call<Job[]>("GET", "/jobs"),
  job: (id: number) => call<Job>("GET", `/jobs/${id}`),
  startJob: (body: { kind: string; book: string; model?: string; label?: string; run_kind?: string; pages?: string }) => call<{ id: number }>("POST", "/jobs", body),
  cancelJob: (id: number) => call<{ cancelled: boolean }>("POST", `/jobs/${id}/cancel`),
  events: (id: number, onEvent: (e: JobEvent) => void): (() => void) => {
    const es = new EventSource(`/api/jobs/${id}/events`, { withCredentials: true });
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data) as JobEvent;
      onEvent(ev);
      if (ev.event === "state" && ["done", "failed", "cancelled"].includes(ev.state)) es.close();
    };
    es.onerror = () => es.close();
    return () => es.close();
  },
  models: () => call<Record<string, ModelEntry>>("GET", "/models"),
  putModels: (body: Record<string, ModelEntry>) => call<Record<string, ModelEntry>>("PUT", "/models", body),
  presets: () => call<Preset[]>("GET", "/models/presets"),
  users: () => call<User[]>("GET", "/users"),
  addUser: (name: string, password: string, role: string) => call<User>("POST", "/users", { name, password, role }),
  placements: () => call<Placement[]>("GET", "/fleet/placements"),
  ledger: () => call<LedgerRow[]>("GET", "/fleet/ledger"),
  stopPlacement: (id: string) => call<{ stopped: string }>("DELETE", `/fleet/placements/${id}`),
};
