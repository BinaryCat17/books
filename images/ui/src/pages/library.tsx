import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api, errorText } from "../api";
import type { BookRow, Job, JobEvent, Preset, User } from "../types";

const KINDS = ["detect", "hybrid", "read", "bench"] as const;
type Kind = (typeof KINDS)[number];
const LIVE = (j: Job) => j.state === "queued" || j.state === "running";

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
      setError(errorText(e));
    }
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(() => api.jobs().then(setJobs, () => undefined), 10000);
    return () => clearInterval(t);
  }, [refresh]);

  const patch = (id: number, fields: Partial<Job>) => setJobs((js) => js.map((j) => (j.id === id ? { ...j, ...fields } : j)));
  const follow = useCallback((id: number) => {
    if (subs.current[id]) return;
    const drop = () => delete subs.current[id];
    subs.current[id] = api.events(
      id,
      (ev: JobEvent) => {
        if (ev.event === "line") {
          setLines((l) => ({ ...l, [id]: [...(l[id] ?? []).slice(-40), ev.text] }));
          if (ev.n != null && ev.of != null) patch(id, { n: ev.n, of: ev.of });
        }
        if (ev.event === "state") {
          patch(id, { state: ev.state, n: ev.n ?? undefined, of: ev.of ?? undefined, error: ev.error ?? null, result: ev.result ?? null });
          if (!["queued", "running"].includes(ev.state)) {
            drop();
            api.books().then(setBooks, () => undefined);
          }
        }
      },
      () => {
        drop();
        api.job(id).then((j) => patch(id, j), () => undefined);
      },
    );
  }, []);
  useEffect(() => {
    jobs.filter(LIVE).forEach((j) => follow(j.id));
  }, [jobs, follow]);
  useEffect(() => () => Object.values(subs.current).forEach((close) => close()), []);

  const start = async (body: Parameters<typeof api.startJob>[0]) => {
    try {
      const { id } = await api.startJob(body);
      setJobs((js) => [{ id, user: user.id, store: "", kind: body.kind, book: body.book, label: body.label ?? "", model: body.model ?? "", args: {}, state: "queued", n: null, of: null, created: Date.now() / 1000, started: null, finished: null, error: null, result: null }, ...js]);
      setError("");
    } catch (e) {
      setError(errorText(e));
    }
  };
  const remove = async (book: string) => {
    if (!window.confirm(`Delete ${book} with all its runs?`)) return;
    try {
      await api.deleteBook(book);
      await refresh();
    } catch (e) {
      setError(errorText(e));
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
                    {r.complete ? <Link to={`/books/${b.name}/runs/${r.kind}/${encodeURIComponent(r.label)}`}>{r.level} · {r.label}</Link> : <span>{r.level} · {r.label}</span>}{" "}
                    <span className="muted">{r.pages} pages{r.complete ? "" : ", unfinished"}</span>
                  </div>
                ))}
              </td>
              <td><Launcher book={b} presets={presets} onStart={start} /></td>
              <td><button onClick={() => remove(b.name)}>delete</button></td>
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
              <td>{LIVE(j) && <button onClick={() => api.cancelJob(j.id).catch((e) => setError(errorText(e)))}>cancel</button>}</td>
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
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="row panel" onSubmit={submit}>
      <input id="upload-file" aria-label="scan" type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <input id="upload-name" aria-label="book name" placeholder="name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
      <button className="primary" type="submit" disabled={!file || busy}>{busy ? "uploading…" : "upload a scan"}</button>
      {error && <span className="err">{error}</span>}
    </form>
  );
}

function Launcher({ book, presets, onStart }: { book: BookRow; presets: Preset[]; onStart: (b: Parameters<typeof api.startJob>[0]) => void }) {
  const [kind, setKind] = useState<Kind>("detect");
  const [model, setModel] = useState("");
  const [run, setRun] = useState("");
  const [pages, setPages] = useState("");
  const wantKind = kind === "read" ? ["reader"] : kind === "hybrid" ? ["hybrid"] : kind === "detect" ? ["layout"] : [];
  const fit = presets.filter((p) => wantKind.includes(p.kind));
  const runs = book.runs.filter((r) => r.complete && (kind === "read" ? r.kind === "detect" : true));
  const needsModel = kind === "detect" || kind === "read" || kind === "hybrid";
  const needsRun = kind === "read" || kind === "bench";
  const chosen = runs.find((r) => `${r.kind}/${r.label}` === run);
  return (
    <div className="row">
      <select id={`kind-${book.name}`} aria-label="job" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
        {KINDS.map((k) => <option key={k}>{k}</option>)}
      </select>
      {needsModel && (
        <select id={`model-${book.name}`} aria-label="model" value={model} onChange={(e) => setModel(e.target.value)}>
          <option value="">model…</option>
          {fit.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
        </select>
      )}
      {needsRun && (
        <select id={`run-${book.name}`} aria-label="run" value={run} onChange={(e) => setRun(e.target.value)}>
          <option value="">{kind === "read" ? "detect run…" : "run…"}</option>
          {runs.map((r) => <option key={r.kind + r.label} value={`${r.kind}/${r.label}`}>{r.level} · {r.label}</option>)}
        </select>
      )}
      <input id={`pages-${book.name}`} aria-label="pages, counted from 1" placeholder="pages from 1 (1-3)" size={12} value={pages} onChange={(e) => setPages(e.target.value)} />
      <button
        className="primary"
        disabled={(needsModel && !model) || (needsRun && !chosen)}
        onClick={() => onStart({ kind, book: book.name, model: needsModel ? model : "", label: chosen?.label ?? "", pages, run_kind: chosen?.kind ?? "detect" })}
      >
        run
      </button>
    </div>
  );
}
