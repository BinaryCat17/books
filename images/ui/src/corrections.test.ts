import { describe, expect, it } from "vitest";

import { correctionOf, draftOf, saysOf } from "./corrections";
import type { Block } from "./types";

const block = { anchor: "p0001-b2", label: "text", content: "the modle said" } as Block;

describe("a correction", () => {
  it("carries only what changed, and nothing when nothing did", () => {
    const d = draftOf(block);
    expect(d).toEqual({ content: "the modle said", label: "text", drop: false });
    expect(correctionOf(block, d)).toBeNull();
    expect(correctionOf(block, { ...d, content: "the model said" })).toEqual({ anchor: "p0001-b2", content: "the model said" });
    expect(correctionOf(block, { ...d, label: "table" })).toEqual({ anchor: "p0001-b2", label: "table" });
    expect(correctionOf(block, { ...d, content: "" })).toEqual({ anchor: "p0001-b2", content: null });
    expect(correctionOf(block, { ...d, content: "x", label: "y", drop: true })).toEqual({ anchor: "p0001-b2", drop: true });
  });
  it("says what it did", () => {
    expect(saysOf({ anchor: "a", drop: true })).toBe("dropped");
    expect(saysOf({ anchor: "a", label: "table", content: null })).toBe("label table, no text");
    expect(saysOf({ anchor: "a", content: "x".repeat(50) })).toBe(`text “${"x".repeat(40)}…”`);
  });
});
