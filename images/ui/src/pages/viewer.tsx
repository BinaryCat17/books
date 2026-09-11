import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, errorText } from "../api";
import type { Block, PageData, Pairs, Record_, RunInfo, Scalar, SeriesRow, User } from "../types";
import { drawOrder, missedOf, summaryOf, verdictsOf } from "../verdicts";
import { Labeler } from "./labeler";

export function Viewer({ user }: { user: User }) {
  const { root = "", name = "", kind = "", label = "" } = useParams();
  const book = `${root}/${name}`;
  const [run, setRun] = useState<RunInfo | null>(null);
  const [index, setIndex] = useState(0);
  const [page, setPage] = useState<PageData | null>(null);
  const [pairs, setPairs] = useState<Pairs | null>(null);
  const [showPairs, setShowPairs] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Record_[] | null>(null);
  const [series, setSeries] = useState<SeriesRow[] | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [labelling, setLabelling] = useState(false);
  const fail = (e: unknown) => setError(errorText(e));
  const canLabel = user.role === "admin" && run?.truth === "own";

  useEffect(() => {
    api.run(book, kind, label).then((r) => { setRun(r); setIndex(r.pages[0] ?? 0); }, fail);
    api.series(book, kind, label).then(setSeries, () => setSeries([]));
  }, [book, kind, label]);
  useEffect(() => {
    if (!run) return;
    setPage(null); setPairs(null); setMetrics(null); setSelected(null);
    api.page(book, kind, label, index).then(setPage, fail);
  }, [run, book, kind, label, index]);
  useEffect(() => {
    if (!run || !run.truth) return;
    if (!showPairs) { setPairs(null); return; }
    api.pairs(book, kind, label, index).then(setPairs, fail);
  }, [run, showPairs, book, kind, label, index]);

  const startTruth = useCallback(async () => {
    setBusy("starting…");
    try {
      await api.startTruth(book, kind, label);
      setRun(await api.run(book, kind, label));
      setLabelling(true);
      setError("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy("");
    }
  }, [book, kind, label]);

  const measure = useCallback(async () => {
    setBusy("measuring…");
    try {
      setMetrics(await api.pageMetrics(book, kind, label, index));
      setError("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy("");
    }
  }, [book, kind, label, index]);

  const verdict = useMemo(() => verdictsOf(pairs), [pairs]);
  const missed = useMemo(() => missedOf(pairs), [pairs]);
  const drawn = useMemo(() => (page ? drawOrder(page.blocks) : []), [page]);
  const sel = page?.blocks.find((b) => b.anchor === selected) ?? null;
  const pageNo = run ? run.pages.indexOf(index) : -1;
  const jump = (v: string) => {
    const n = Number(v);
    if (run && run.pages.includes(n)) setIndex(n);
  };

  if (error && !run) return <div className="err">{error}</div>;
  if (!run) return <div className="muted">…</div>;
  return (
    <>
      <div className="row" style={{ marginBottom: 8 }}>
        <Link to="/">← library</Link>
        <h1 style={{ margin: 0 }}>{book} · {run.level} · {label}</h1>
        <span className="muted mono">{run.identity?.slice(0, 12)}</span>
        <span style={{ flex: 1 }} />
        <a href={api.documentUrl(book, kind, label)} target="_blank" rel="noreferrer">document.json</a>
      </div>
      {error && <div className="err">{error}</div>}
      <div className="row" style={{ marginBottom: 8 }}>
        <button aria-label="previous page" disabled={pageNo <= 0} onClick={() => setIndex(run.pages[pageNo - 1])}>‹</button>
        <span>page <input aria-label="page index" className="mono" style={{ width: 60 }} value={index} onChange={(e) => jump(e.target.value)} /> <span className="muted">({pageNo + 1} of {run.pages.length})</span></span>
        <button aria-label="next page" disabled={pageNo >= run.pages.length - 1} onClick={() => setIndex(run.pages[pageNo + 1])}>›</button>
        {run.truth && (
          <label><input type="checkbox" checked={showPairs} onChange={(e) => setShowPairs(e.target.checked)} /> against truth</label>
        )}
        <button onClick={measure} disabled={!!busy}>{busy || "measure this page"}</button>
        {run.truth === "borrowed" && <span className="muted">truth borrowed from a bench with this scan</span>}
        {user.role === "admin" && run.truth === null && <button onClick={startTruth} disabled={!!busy}>start truth</button>}
        {canLabel && <button onClick={() => setLabelling(!labelling)}>{labelling ? "viewing" : "label"}</button>}
        <span className="legend">
          <span><i style={{ borderColor: "var(--text)" }} />text</span>
          <span><i style={{ borderColor: "var(--artifact)" }} />artifact</span>
          <span><i style={{ borderColor: "var(--furniture)" }} />furniture</span>
          {showPairs && <><span><i style={{ borderColor: "var(--truth)", borderStyle: "dashed" }} />truth</span><span><i style={{ borderColor: "var(--missed)" }} />missed</span><span><i style={{ borderColor: "var(--extra)", borderStyle: "dashed" }} />spurious</span><span><i style={{ borderColor: "var(--label)" }} />label differs</span></>}
        </span>
      </div>
      {labelling && canLabel ? <Labeler book={book} run={run} index={index} page={page} onDone={() => setLabelling(false)} /> : (
      <div className="viewer">
        <div className="sheet">
          <img src={api.imageUrl(book, index)} alt={`page ${index}`} />
          {page && (
            <svg viewBox={`0 0 ${page.width} ${page.height}`} preserveAspectRatio="none">
              {pairs?.truth?.map((t) => <rect key={"t" + t.anchor} className="truth" x={t.box[0]} y={t.box[1]} width={t.box[2] - t.box[0]} height={t.box[3] - t.box[1]} />)}
              {drawn.map((b) => (
                <rect
                  key={b.anchor}
                  className={`${b.role} ${verdict[b.anchor] ?? ""} ${selected === b.anchor ? "sel" : ""}`}
                  x={b.box[0]} y={b.box[1]} width={b.box[2] - b.box[0]} height={b.box[3] - b.box[1]}
                  onClick={() => setSelected(b.anchor)}
                >
                  <title>{b.anchor} {b.label} ({b.role}){verdict[b.anchor] ? ` · ${verdict[b.anchor]}` : ""}</title>
                </rect>
              ))}
              {missed.map((t) => <rect key={"m" + t.anchor} className="missed" x={t.box[0]} y={t.box[1]} width={t.box[2] - t.box[0]} height={t.box[3] - t.box[1]} />)}
            </svg>
          )}
        </div>
        <div className="side">
          {page && (
            <div className="panel">
              <h2 style={{ marginTop: 0 }}>Page {index}</h2>
              <div className="muted">{page.blocks.length} blocks · order {page.order_source}{page.trouble ? ` · ${page.trouble}` : ""}{page.repeats_verbatim ? ` · ${page.repeats_verbatim} repeats` : ""}</div>
              {pairs && <div className="muted">{summaryOf(pairs)}</div>}
              <div className="block-list">
                <table>
                  <tbody>
                    {page.blocks.map((b) => (
                      <tr key={b.anchor} className={selected === b.anchor ? "sel" : ""} onClick={() => setSelected(b.anchor)} style={{ cursor: "pointer" }}>
                        <td className="mono">{b.anchor}</td><td>{b.label}</td><td className="muted">{b.role}</td><td>{verdict[b.anchor] ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {sel && <BlockDetail block={sel} crop={api.cropUrl(book, kind, label, sel.anchor)} />}
          {metrics && <MetricsPanel title={`Metrics on page ${index}`} records={metrics} />}
          {series && series.length > 0 && <SeriesPanel rows={series} />}
          {user.role === "admin" && pairs?.pairs.some((p) => p.why) && (
            <div className="panel">
              <h2 style={{ marginTop: 0 }}>Why missed</h2>
              {pairs.pairs.filter((p) => p.why).map((p) => <div key={p.truth}><span className="mono">{p.truth}</span> {p.why} {p.fate && <span className="muted">({p.fate})</span>}</div>)}
            </div>
          )}
        </div>
      </div>
      )}
    </>
  );
}

function BlockDetail({ block, crop }: { block: Block; crop: string }) {
  const r = block.reading;
  return (
    <div className="panel detail">
      <h2 style={{ marginTop: 0 }}>{block.anchor}</h2>
      <dl>
        <dt>label · class · role</dt><dd>{block.label} · {block.cls} · {block.role}</dd>
        <dt>score · order</dt><dd>{block.score == null ? "—" : block.score.toFixed(3)} · {block.order ?? "—"} ({block.order_source})</dd>
        <dt>box</dt><dd className="mono">{block.box.map((v) => Math.round(v)).join(", ")}</dd>
        {block.as_picture && <><dt>shown as</dt><dd>a picture{block.why_empty ? ` (${block.why_empty})` : ""}</dd></>}
        {block.repeat_of && <><dt>repeat</dt><dd>{block.repeat_verdict} of {block.repeat_of}</dd></>}
        {block.inside && <><dt>inside</dt><dd className="mono">{block.inside}</dd></>}
        {block.hit_ceiling && <><dt>reading</dt><dd className="err">cut off by the ceiling</dd></>}
        {block.table_shape && <><dt>table</dt><dd className="err">{block.table_shape}</dd></>}
        {r && <><dt>read</dt><dd className="muted">{String(r.outcome ?? "")} {String(r.kind_sniffed ?? "")}</dd></>}
      </dl>
      <img src={crop} alt={block.anchor} style={{ maxWidth: "100%", border: "1px solid var(--rule)" }} />
      {block.content && <div className="content">{block.content}</div>}
    </div>
  );
}

export function fmt(s: Scalar): string {
  if (s.value == null) return "—";
  return Number.isInteger(s.value) ? String(s.value) : s.value.toFixed(3);
}

function MetricsPanel({ title, records }: { title: string; records: Record_[] }) {
  return (
    <div className="panel">
      <h2 style={{ marginTop: 0 }}>{title}</h2>
      {records.length === 0 && <div className="muted">no metric applies</div>}
      {records.map((rec) => (
        <table key={rec.metric}>
          <thead><tr><th>{rec.metric}</th><th>value</th><th>count</th></tr></thead>
          <tbody>
            {Object.entries(rec.scalars).map(([k, s]) => (
              <tr key={k}><td>{k}</td><td>{fmt(s)}{s.why && <span className="muted"> {s.why}</span>}</td><td className="muted">{s.count ? `${s.count.n}/${s.count.of}` : s.over ? `${s.over.n}/${s.over.of} ${s.over.unit}` : ""}</td></tr>
            ))}
          </tbody>
        </table>
      ))}
    </div>
  );
}

function SeriesPanel({ rows }: { rows: SeriesRow[] }) {
  const last = rows[rows.length - 1].when;
  const latest = rows.filter((r) => r.when === last);
  const when = new Date(last * 1000).toLocaleString();
  return (
    <div className="panel">
      <h2 style={{ marginTop: 0 }}>Book · measured {when}</h2>
      {latest.map((rec) => (
        <table key={rec.id}>
          <thead><tr><th>{rec.metric} <span className={rec.state === "current" ? "ok" : "err"}>{rec.state}</span></th><th>value</th></tr></thead>
          <tbody>
            {Object.entries(rec.scalars).map(([k, s]) => <tr key={k}><td>{k}</td><td>{fmt(s)}{s.why && <span className="muted"> {s.why}</span>}</td></tr>)}
          </tbody>
        </table>
      ))}
      <div className="muted">{new Set(rows.map((r) => r.when)).size} measurements in the series</div>
    </div>
  );
}
