import { describe, expect, it } from "vitest";

import { messageOf } from "./api";
import { drawOrder, missedOf, summaryOf, verdictsOf } from "./verdicts";
import type { Block, Pairs } from "./types";

describe("the error text of an answer", () => {
  it("takes the backend's error, a plain detail, a structured detail, or the status", () => {
    expect(messageOf({ error: "no such user" }, "x")).toBe("no such user");
    expect(messageOf({ detail: "this needs the admin role" }, "x")).toBe("this needs the admin role");
    expect(messageOf({ detail: [{ loc: ["body"], msg: "field required" }] }, "x")).toContain("field required");
    expect(messageOf("<html>", "Bad Gateway")).toBe("Bad Gateway");
    expect(messageOf(null, "status 0")).toBe("status 0");
  });
});

const pairs: Pairs = {
  index: 0, labelled: "not_said", compared: true,
  pairs: [
    { truth: "p0000-b0", verdict: "matched", run: "p0000-b0", label_ok: true, fate: null },
    { truth: "p0000-b1", verdict: "matched", run: "p0000-b1", label_ok: false, fate: "intact" },
    { truth: "p0000-b2", verdict: "missed", run: null, label_ok: null, fate: "not_seen", why: "not seen" },
  ],
  extras: [{ run: "p0000-b7", verdict: "spurious_box" }, { run: "p0000-b8", verdict: "not counted" }, { run: "p0000-b1", verdict: "nested duplicate" }],
  truth: [{ anchor: "p0000-b2", block_id: 2, label: "table", box: [0, 0, 1, 1], order: 2 }],
};

describe("the verdict on each run box", () => {
  it("is one per box, the extra's word first, then the pair's label agreement", () => {
    expect(verdictsOf(pairs)).toEqual({ "p0000-b0": "matched", "p0000-b1": "extra", "p0000-b7": "spurious", "p0000-b8": "extra" });
    expect(verdictsOf(null)).toEqual({});
  });
  it("names the truth blocks that were missed and sums the page", () => {
    expect(missedOf(pairs).map((t) => t.anchor)).toEqual(["p0000-b2"]);
    expect(summaryOf(pairs)).toBe("2 matched, 1 missed, 1 spurious, 2 extra not counted");
    expect(summaryOf({ ...pairs, compared: false, labelled: "no" })).toBe("not compared (labelled: no)");
  });
});

describe("the drawing order", () => {
  it("puts small boxes over large ones so every box can be clicked", () => {
    const b = (anchor: string, box: [number, number, number, number]) => ({ anchor, box }) as Block;
    const out = drawOrder([b("small", [0, 0, 1, 1]), b("big", [0, 0, 10, 10]), b("mid", [0, 0, 5, 5])]);
    expect(out.map((x) => x.anchor)).toEqual(["big", "mid", "small"]);
  });
});
