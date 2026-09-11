import type { Block, Correction } from "./types";

export type Draft = { content: string; label: string; drop: boolean };

export function draftOf(block: Block): Draft {
  return { content: block.content ?? "", label: block.label, drop: false };
}

export function correctionOf(block: Block, draft: Draft): Correction | null {
  const out: Correction = { anchor: block.anchor };
  if (draft.drop) out.drop = true;
  else {
    if (draft.content !== (block.content ?? "")) out.content = draft.content === "" ? null : draft.content;
    if (draft.label !== block.label) out.label = draft.label;
  }
  return Object.keys(out).length > 1 ? out : null;
}

export function saysOf(c: Correction): string {
  if (c.drop) return "dropped";
  const parts = [];
  if (c.label !== undefined) parts.push(`label ${c.label}`);
  if (c.content !== undefined) parts.push(c.content === null ? "no text" : `text “${c.content.length > 40 ? c.content.slice(0, 40) + "…" : c.content}”`);
  return parts.join(", ");
}
