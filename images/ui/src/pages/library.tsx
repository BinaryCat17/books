import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api";
import type { BookRow, Job, JobEvent, Preset, User } from "../types";

const KINDS = ["detect", "hybrid", "read", "bench", "html"] as const;

export function Library({ user }: { user: User }) {
  const [books, setBooks] = useState<BookRow[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [lines, setLines] = useState<Record<number, string[]>>({});
  const [error, setError] = useState("");
  const subs = useRef<Record<number, () => void>>({});

  const refresh = useCallback(async () => {
    try {
      const [b, p, j] = await Promise.all([api.books(), api.presets(), api.jobs()]);
      setBooks(b);
      setPresets(p);
      setJobs(j);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  const follow = useCallback((id: number) => {
    if (subs.current[id]) return;
    subs.current[id] = api.events(id, (ev: JobEvent) => {
      if (ev.event === "line") setLines((l) => ({ ...l, [id]: [...(l[id] ?? []).slice(-40), ev.text] }));
      if (ev.event === "state") {
        setJobs((js) => js.map((j) => (j.id === id ? { ...j, state: ev.state, n: ev.n ?? j.n, of: ev.of ?? j.of, error: ev.error ?? j.error, result: ev.result ?? j.result } : j)));
        if (["done", "failed", "cancelled"].includes(ev.state)) {
          delete subs.current[id];
          api.books().then(setBooks);
        }
      }
    });
  }, []);
  useEffect(() => {
    jobs.filter((j) => j.state === "queued" || j.state === "running").forEach((j) => follow(j.id));
  }, [jobs, follow]);
  useEffect(() => () => Object.values(subs.current).forEach((close) => close()), []);

  const start = async (body: Parameters<typeof api.startJob>[0]) => {
    try {
      const { id } = await api.startJob(body);
      setJobs((js) => [{ id, user: user.id, kind: body.kind, book: body.book, label: body.label ?? "", model: body.model ?? "", state: "queued", n: null, of: null, created: Date.now() / 1000, started: null, finished: null, error: null, result: null }, ...js]);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  return (
    <>
      <h1>Library</h1>
      {error && <div className="err">{error}</div>}
      <Upload onDone={refresh} />
      <h2>Books</h2>
      <table>
        <thead><tr><th>book</th><th>runs</th><th>start</th><th></th></tr></thead>
        <tbody>
          {books.map((b) => (
            <tr key={b.name}>
              <td className="mono">{b.name}</td>
              <td>
                {b.runs.length === 0 && <span className="muted">none</span>}
                {b.runs.map((r) => (
                  <div key={r.kind + r.label}>
                    <Link to={`/books/${b.name}/runs/${r.kind}/${encodeURIComponent(r.label)}`}>{r.level} · {r.label}</Link>{" "}
                    <span className="muted">{r.pages} pages{r.complete ? "" : ", unfinished"}</span>
                  </div>
                ))}
              </td>
              <td><Launcher book={b} presets={presets} onStart={start} /></td>
              <td><button onClick={() => api.deleteBook(b.name).then(refresh, (e) => setError(String(e)))}>delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Jobs</h2>
      <table>
        <thead><tr><th>#</th><th>kind</th><th>book</th><th>model</th><th>state</th><th>progress</th><th>result</th><th></th></tr></thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <td>{j.id}</td><td>{j.kind}</td><td className="mono">{j.book}</td><td>{j.model || j.label}</td>
              <td><span className={`pill ${j.state}`}>{j.state}</span></td>
              <td>{j.n != null && j.of != null ? `${j.n} / ${j.of}` : ""}</td>
              <td className="mono">{j.error ? <span className="err">{j.error}</span> : j.result}{lines[j.id] && j.state === "running" && <div className="log">{lines[j.id].slice(-3).join("\n")}</div>}</td>
              <td>{(j.state === "queued" || j.state === "running") && <button onClick={() => api.cancelJob(j.id)}>cancel</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Upload({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      await api.upload(file, name);
      setFile(null);
      setName("");
      setError("");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="row panel" onSubmit={submit}>
      <input id="upload-file" type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <input id="upload-name" placeholder="name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
      <button className="primary" type="submit" disabled={!file || busy}>{busy ? "uploading…" : "upload a scan"}</button>
      {error && <span className="err">{error}</span>}
    </form>
  );
}

function Launcher({ book, presets, onStart }: { book: BookRow; presets: Preset[]; onStart: (b: Parameters<typeof api.startJob>[0]) => void }) {
  const [kind, setKind] = useState<(typeof KINDS)[number]>("detect");
  const [model, setModel] = useState("");
  const [label, setLabel] = useState("");
  const [pages, setPages] = useState("");
  const wantKind = kind === "read" ? ["reader"] : kind === "hybrid" ? ["hybrid"] : kind === "detect" ? ["layout"] : [];
  const fit = presets.filter((p) => wantKind.includes(p.kind));
  const detects = book.runs.filter((r) => r.kind === "detect");
  const needsModel = kind === "detect" || kind === "read" || kind === "hybrid";
  const needsLabel = kind === "read" || kind === "bench" || kind === "html";
  return (
    <div className="row">
      <select id={`kind-${book.name}`} value={kind} onChange={(e) => setKind(e.target.value as (typeof KINDS)[number])}>
        {KINDS.map((k) => <option key={k}>{k}</option>)}
      </select>
      {needsModel && (
        <select id={`model-${book.name}`} value={model} onChange={(e) => setModel(e.target.value)}>
          <option value="">model…</option>
          {fit.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
        </select>
      )}
      {needsLabel && (
        <select id={`label-${book.name}`} value={label} onChange={(e) => setLabel(e.target.value)}>
          <option value="">detect run…</option>
          {detects.map((r) => <option key={r.label} value={r.label}>{r.label}</option>)}
        </select>
      )}
      <input id={`pages-${book.name}`} placeholder="pages (1-3)" size={9} value={pages} onChange={(e) => setPages(e.target.value)} />
      <button
        className="primary"
        disabled={(needsModel && !model) || (needsLabel && !label)}
        onClick={() => onStart({ kind, book: book.name, model: needsModel ? model : "", label: needsLabel ? label : "", pages, run_kind: "detect" })}
      >
        run
      </button>
    </div>
  );
}
