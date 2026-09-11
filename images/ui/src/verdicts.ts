import type { Block, Pairs, TruthBlock } from "./types";

export type Verdict = "matched" | "label" | "spurious" | "extra";

export function verdictsOf(pairs: Pairs | null): Record<string, Verdict> {
  const m: Record<string, Verdict> = {};
  if (!pairs) return m;
  for (const e of pairs.extras) m[e.run] = e.verdict === "spurious_box" ? "spurious" : "extra";
  for (const p of pairs.pairs) if (p.run && !(p.run in m)) m[p.run] = p.label_ok === false ? "label" : "matched";
  return m;
}

export function missedOf(pairs: Pairs | null): TruthBlock[] {
  if (!pairs?.truth) return [];
  const missed = new Set(pairs.pairs.filter((p) => p.verdict === "missed").map((p) => p.truth));
  return pairs.truth.filter((t) => missed.has(t.anchor));
}

export function summaryOf(pairs: Pairs): string {
  if (!pairs.compared) return `not compared (labelled: ${pairs.labelled})`;
  const matched = pairs.pairs.filter((p) => p.verdict === "matched").length;
  const missed = pairs.pairs.length - matched;
  const spurious = pairs.extras.filter((e) => e.verdict === "spurious_box").length;
  const other = pairs.extras.length - spurious;
  return `${matched} matched, ${missed} missed, ${spurious} spurious${other ? `, ${other} extra not counted` : ""}`;
}

export function drawOrder(blocks: Block[]): Block[] {
  const area = (b: Block) => (b.box[2] - b.box[0]) * (b.box[3] - b.box[1]);
  return [...blocks].sort((a, b) => area(b) - area(a));
}
