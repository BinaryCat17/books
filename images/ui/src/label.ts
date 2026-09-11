import type { Block, ClassTable, RunInfo, TruthBlockRaw, TruthPage } from "./types";

export type Choice = { label: string; cls: string };
export type Box = [number, number, number, number];

export function choicesOf(policy: RunInfo["policy"], table: ClassTable | null): Choice[] {
  const own = policy.classes && Object.keys(policy.classes).length ? policy.classes : null;
  const classes = own ?? Object.fromEntries(Object.keys(table?.classes ?? {}).map((c) => [c, c]));
  return Object.entries(classes)
    .map(([label, cls]) => ({ label, cls }))
    .sort((a, b) => a.cls.localeCompare(b.cls) || a.label.localeCompare(b.label));
}

export function roleOf(label: string, choices: Choice[], table: ClassTable | null): string {
  const cls = choices.find((c) => c.label === label)?.cls ?? label;
  return table?.classes[cls]?.role ?? "text";
}

export function normalBox(x0: number, y0: number, x1: number, y1: number, width: number, height: number): Box {
  const clamp = (v: number, hi: number) => Math.min(hi, Math.max(0, Math.round(v * 10) / 10));
  return [clamp(Math.min(x0, x1), width), clamp(Math.min(y0, y1), height), clamp(Math.max(x0, x1), width), clamp(Math.max(y0, y1), height)];
}

export function toRaster(clientX: number, clientY: number, rect: { left: number; top: number; width: number; height: number }, page: { width: number; height: number }): [number, number] {
  return [((clientX - rect.left) / rect.width) * page.width, ((clientY - rect.top) / rect.height) * page.height];
}

export function renumbered(page: TruthPage): TruthPage {
  return { ...page, blocks: page.blocks.map((b, i) => ({ ...b, order: i })) };
}

export function withBox(page: TruthPage, box: Box, label: string): TruthPage {
  const id = page.blocks.reduce((m, b) => Math.max(m, b.block_id + 1), 0);
  const block: TruthBlockRaw = { block_id: id, box, label, score: null, order: page.blocks.length, content: null, kind: "none" };
  return { ...page, blocks: [...page.blocks, block] };
}

export function without(page: TruthPage, blockId: number): TruthPage {
  return renumbered({ ...page, blocks: page.blocks.filter((b) => b.block_id !== blockId) });
}

export function relabelled(page: TruthPage, blockId: number, label: string): TruthPage {
  return { ...page, blocks: page.blocks.map((b) => (b.block_id === blockId ? { ...b, label } : b)) };
}

export function moved(page: TruthPage, blockId: number, delta: -1 | 1): TruthPage {
  const i = page.blocks.findIndex((b) => b.block_id === blockId);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= page.blocks.length) return page;
  const blocks = [...page.blocks];
  [blocks[i], blocks[j]] = [blocks[j], blocks[i]];
  return renumbered({ ...page, blocks });
}

export function fromRun(page: TruthPage, blocks: Block[]): TruthPage {
  const taken = [...blocks].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  return renumbered({
    ...page,
    blocks: taken.map((b, i) => ({ block_id: i, box: b.box, label: b.label, score: null, order: i, content: b.content, kind: b.kind === "none" ? "none" : b.kind })),
  });
}

export function withTrait(page: TruthPage, trait: "labelled" | "text_marked" | "order_marked", value: boolean): TruthPage {
  return { ...page, meta: { ...(page.meta ?? {}), [trait]: value } };
}

export function trait(page: TruthPage, name: string): boolean {
  return page.meta?.[name] === true;
}
