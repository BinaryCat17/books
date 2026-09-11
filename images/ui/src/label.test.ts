import { describe, expect, it } from "vitest";

import { choicesOf, fromRun, moved, normalBox, relabelled, roleOf, scaleOf, toRaster, withBox, withTrait, without } from "./label";
import type { Block, ClassTable, TruthPage } from "./types";

const table: ClassTable = {
  classes: { text: { role: "text", order: "text" }, table: { role: "artifact", order: "table" }, caption: { role: "text", order: "caption" } },
  roles: {},
  vocabularies: {},
};
const page: TruthPage = { index: 2, width: 800, height: 1200, dpi: 96, blocks: [], meta: {} };

describe("the labels an admin may draw", () => {
  it("are the run's vocabulary sorted by class, else the class table itself", () => {
    const own = choicesOf({ classes: { figure_title: "caption", paragraph: "text", table: "table" } }, table);
    expect(own.map((c) => c.label)).toEqual(["figure_title", "table", "paragraph"]);
    expect(choicesOf({}, table).map((c) => c.label)).toEqual(["caption", "table", "text"]);
    expect(roleOf("figure_title", own, table)).toBe("text");
    expect(roleOf("table", own, table)).toBe("artifact");
    expect(roleOf("unknown", own, table)).toBe("text");
  });
});

describe("a box drawn on the page", () => {
  it("is normalised, clamped and in raster coordinates", () => {
    expect(normalBox(500, 700, 100, 50, 800, 1200)).toEqual([100, 50, 500, 700]);
    expect(normalBox(-10, 20, 900, 1300, 800, 1200)).toEqual([0, 20, 800, 1200]);
    expect(toRaster(150, 140, { left: 100, top: 100, width: 400, height: 600 }, page)).toEqual([100, 80]);
    expect(scaleOf(page, { width: 400, height: 300 })).toEqual([2, 4]);
  });
  it("joins the page with the next id and the last order; removal renumbers", () => {
    let p = withBox(page, [1, 2, 3, 4], "text");
    p = withBox(p, [5, 6, 7, 8], "table");
    expect(p.blocks.map((b) => [b.block_id, b.order, b.label])).toEqual([[0, 0, "text"], [1, 1, "table"]]);
    p = without(withBox(p, [9, 9, 10, 10], "caption"), 1);
    expect(p.blocks.map((b) => [b.block_id, b.order])).toEqual([[0, 0], [2, 1]]);
    expect(relabelled(p, 2, "text").blocks[1].label).toBe("text");
    expect(moved(p, 2, -1).blocks.map((b) => [b.block_id, b.order])).toEqual([[2, 0], [0, 1]]);
    expect(moved(p, 2, 1)).toBe(p);
    expect(withTrait(p, "labelled", true).meta).toEqual({ labelled: true });
    expect(page.blocks).toEqual([]);
  });
  it("can start from the run's boxes in their reading order", () => {
    const run = [
      { anchor: "p0002-b3", block_id: 3, label: "table", box: [1, 1, 2, 2], order: 1, content: null, kind: "none" },
      { anchor: "p0002-b1", block_id: 1, label: "paragraph", box: [0, 0, 1, 1], order: 0, content: "hi", kind: "text" },
    ] as unknown as Block[];
    const p = fromRun(page, run, page);
    expect(p.blocks.map((b) => [b.block_id, b.order, b.label, b.content])).toEqual([[0, 0, "paragraph", "hi"], [1, 1, "table", null]]);
    const other = fromRun(page, run, { width: 400, height: 300 });
    expect(other.blocks.map((b) => b.box)).toEqual([[0, 0, 2, 4], [2, 4, 4, 8]]);
  });
});
