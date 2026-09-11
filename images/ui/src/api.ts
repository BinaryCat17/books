import type { BookRow, ClassTable, Correction, Corrections, Format, Job, JobEvent, Layer, LedgerRow, ModelEntry, PageData, Pairs, Placement, Preset, Record_, RunInfo, SeriesRow, TruthPage, User } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function messageOf(data: unknown, fallback: string): string {
  const d = data as { error?: unknown; detail?: unknown } | null;
  if (d && typeof d.error === "string") return d.error;
  if (d && d.detail !== undefined) return typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
  return fallback;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

async function call<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  let r: Response;
  try {
    r = await fetch("/api" + path, {
      method,
      credentials: "same-origin",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch (e) {
    throw new ApiError(0, `the server did not answer: ${errorText(e)}`);
  }
  const text = await r.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!r.ok) throw new ApiError(r.status, messageOf(data, r.statusText || `status ${r.status}`));
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
  run: (book: string, kind: string, label: string) => call<RunInfo>("GET", run(book, kind, label)),
  page: (book: string, kind: string, label: string, i: number) => call<PageData>("GET", `${run(book, kind, label)}/pages/${i}`),
  pairs: (book: string, kind: string, label: string, i: number) => call<Pairs>("GET", `${run(book, kind, label)}/pages/${i}/pairs`),
  pageMetrics: (book: string, kind: string, label: string, i: number) => call<Record_[]>("GET", `${run(book, kind, label)}/pages/${i}/metrics`),
  series: (book: string, kind: string, label: string) => call<SeriesRow[]>("GET", `${run(book, kind, label)}/series`),
  imageUrl: (book: string, i: number, dpi = 110) => `/api/books/${book}/pages/${i}/image?dpi=${dpi}`,
  cropUrl: (book: string, kind: string, label: string, anchor: string) => `/api${run(book, kind, label)}/crops/${anchor}`,
  documentUrl: (book: string, kind: string, label: string) => `/api${run(book, kind, label)}/document`,
  exportUrl: (book: string, kind: string, label: string, fmt: Format) => `/api${run(book, kind, label)}/export/${fmt}`,
  corrections: (book: string, kind: string, label: string) => call<Corrections>("GET", `${run(book, kind, label)}/corrections`),
  correct: (book: string, kind: string, label: string, body: Correction) => call<Corrections>("POST", `${run(book, kind, label)}/corrections`, body),
  uncorrect: (book: string, kind: string, label: string, n: number) => call<Corrections>("DELETE", `${run(book, kind, label)}/corrections/${n}`),
  truthPage: (book: string, i: number) => call<TruthPage>("GET", `/books/${book}/truth/pages/${i}`),
  putTruthPage: (book: string, i: number, page: TruthPage) => call<Layer>("PUT", `/books/${book}/truth/pages/${i}`, page),
  startTruth: (book: string, kind: string, label: string) => call<{ truth: string; pages: number; dpi: number }>("POST", `/books/${book}/truth`, { kind, label }),
  classes: () => call<ClassTable>("GET", "/classes"),
  jobs: () => call<Job[]>("GET", "/jobs"),
  job: (id: number) => call<Job>("GET", `/jobs/${id}`),
  startJob: (body: { kind: string; book: string; model?: string; label?: string; run_kind?: string; pages?: string }) => call<{ id: number }>("POST", "/jobs", body),
  cancelJob: (id: number) => call<{ cancelled: boolean }>("POST", `/jobs/${id}/cancel`),
  events: (id: number, onEvent: (e: JobEvent) => void, onError: () => void): (() => void) => {
    const es = new EventSource(`/api/jobs/${id}/events`, { withCredentials: true });
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data) as JobEvent;
      onEvent(ev);
      if (ev.event === "state" && ["done", "failed", "cancelled"].includes(ev.state)) es.close();
    };
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) onError();
    };
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
