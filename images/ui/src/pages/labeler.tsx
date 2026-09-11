import { useEffect, useRef, useState } from "react";

import { api, errorText } from "../api";
import { choicesOf, fromRun, moved, normalBox, relabelled, roleOf, scaleOf, toRaster, trait, withBox, withTrait, without, type Box, type Choice } from "../label";
import type { ClassTable, PageData, RunInfo, TruthPage } from "../types";

const TRAITS = ["labelled", "text_marked", "order_marked"] as const;
const LEAST = 4;

export function Labeler({ book, run, index, page, onDone }: { book: string; run: RunInfo; index: number; page: PageData | null; onDone: () => void }) {
  const [table, setTable] = useState<ClassTable | null>(null);
  const [truth, setTruth] = useState<TruthPage | null>(null);
  const [saved, setSaved] = useState<TruthPage | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [drawAs, setDrawAs] = useState("");
  const [draft, setDraft] = useState<Box | null>(null);
  const [showRun, setShowRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const start = useRef<[number, number] | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const choices: Choice[] = choicesOf(run.policy, table);
  const dirty = truth !== saved;

  useEffect(() => { api.classes().then(setTable, (e) => setError(errorText(e))); }, []);
  useEffect(() => {
    let live = true;
    setTruth(null); setSaved(null); setSelected(null); setDraft(null);
    api.truthPage(book, index).then((t) => { if (live) { setTruth(t); setSaved(t); } }, (e) => { if (live) setError(errorText(e)); });
    return () => { live = false; };
  }, [book, index]);
  useEffect(() => { if (!drawAs && choices.length) setDrawAs((choices.find((c) => c.label === "text") ?? choices.find((c) => c.cls === "text") ?? choices[0]).label); }, [choices, drawAs]);

  const at = (e: React.PointerEvent): [number, number] | null => {
    if (!truth || !svg.current) return null;
    return toRaster(e.clientX, e.clientY, svg.current.getBoundingClientRect(), truth);
  };
  const down = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    const p = at(e);
    if (!p) return;
    start.current = p;
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const p = at(e);
    if (!p || !start.current || !truth) return;
    setDraft(normalBox(start.current[0], start.current[1], p[0], p[1], truth.width, truth.height));
  };
  const cancel = () => { start.current = null; setDraft(null); };
  const up = (e: React.PointerEvent<SVGSVGElement>) => {
    const p = at(e);
    const s = start.current;
    cancel();
    if (!p || !s || !truth) return;
    const box = normalBox(s[0], s[1], p[0], p[1], truth.width, truth.height);
    if (box[2] - box[0] < LEAST || box[3] - box[1] < LEAST) return;
    const next = withBox(truth, box, drawAs);
    setTruth(next);
    setSelected(next.blocks[next.blocks.length - 1].block_id);
  };
  const save = async () => {
    if (!truth) return;
    setBusy(true);
    try {
      const got = await api.putTruthPage(book, index, truth);
      setTruth(got.page); setSaved(got.page); setError("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="row" style={{ marginBottom: 8 }}>
        <span>draw as <select aria-label="draw as" value={drawAs} onChange={(e) => setDrawAs(e.target.value)}>{choices.map((c) => <option key={c.label} value={c.label}>{c.label}{c.cls !== c.label ? ` (${c.cls})` : ""}</option>)}</select></span>
        <label><input type="checkbox" checked={showRun} onChange={(e) => setShowRun(e.target.checked)} /> show the run</label>
        {page && truth && <button onClick={() => { setTruth(fromRun(truth, page.blocks, page)); setSelected(null); }}>take the run's boxes</button>}
        <span style={{ flex: 1 }} />
        <button className="primary" disabled={!dirty || busy} onClick={save}>{busy ? "saving…" : "save layer"}</button>
        <button disabled={!dirty || busy} onClick={() => { setTruth(saved); setSelected(null); }}>discard</button>
        <button disabled={busy} onClick={onDone}>done</button>
      </div>
      {error && <div className="err">{error}</div>}
      <div className="viewer">
        <div className="sheet label">
          <img src={api.imageUrl(book, index)} alt={`page ${index}`} draggable={false} />
          {truth && (
            <svg ref={svg} viewBox={`0 0 ${truth.width} ${truth.height}`} preserveAspectRatio="none" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={cancel}>
              {showRun && page && (
                <g transform={`scale(${scaleOf(truth, page).join(" ")})`}>
                  {page.blocks.map((b) => <rect key={"r" + b.anchor} className={`ghost ${b.role}`} x={b.box[0]} y={b.box[1]} width={b.box[2] - b.box[0]} height={b.box[3] - b.box[1]} />)}
                </g>
              )}
              {truth.blocks.map((b) => (
                <rect
                  key={b.block_id}
                  className={`edit ${roleOf(b.label, choices, table)} ${selected === b.block_id ? "sel" : ""}`}
                  x={b.box[0]} y={b.box[1]} width={b.box[2] - b.box[0]} height={b.box[3] - b.box[1]}
                  onPointerDown={() => setSelected(b.block_id)}
                >
                  <title>{b.order} {b.label}</title>
                </rect>
              ))}
              {draft && <rect className="draft" x={draft[0]} y={draft[1]} width={draft[2] - draft[0]} height={draft[3] - draft[1]} />}
            </svg>
          )}
        </div>
        <div className="side">
          {truth && (
            <div className="panel">
              <h2 style={{ marginTop: 0 }}>Truth on page {index}{dirty && <span className="err"> · unsaved</span>}</h2>
              <div className="row">
                {TRAITS.map((t) => <label key={t}><input type="checkbox" checked={trait(truth, t)} onChange={(e) => setTruth(withTrait(truth, t, e.target.checked))} /> {t}</label>)}
              </div>
              {truth.meta?.author != null && <div className="muted">last layer by {String(truth.meta.author)} at {String(truth.meta.when)}</div>}
              <div className="block-list">
                <table>
                  <tbody>
                    {truth.blocks.map((b, i) => (
                      <tr key={b.block_id} className={selected === b.block_id ? "sel" : ""} onClick={() => setSelected(b.block_id)}>
                        <td className="mono">{i}</td>
                        <td><select aria-label={`label of block ${b.block_id}`} value={b.label} onChange={(e) => setTruth(relabelled(truth, b.block_id, e.target.value))}>{[...new Set([b.label, ...choices.map((c) => c.label)])].map((l) => <option key={l} value={l}>{l}</option>)}</select></td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          <button aria-label="up" disabled={i === 0} onClick={() => setTruth(moved(truth, b.block_id, -1))}>↑</button>
                          <button aria-label="down" disabled={i === truth.blocks.length - 1} onClick={() => setTruth(moved(truth, b.block_id, 1))}>↓</button>
                          <button aria-label="delete" onClick={() => { setTruth(without(truth, b.block_id)); if (selected === b.block_id) setSelected(null); }}>×</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {truth.blocks.length === 0 && <div className="muted">drag on the page to draw a box</div>}
              {selected != null && <div className="mono muted">box {truth.blocks.find((b) => b.block_id === selected)?.box.map((v) => Math.round(v)).join(", ")}</div>}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
