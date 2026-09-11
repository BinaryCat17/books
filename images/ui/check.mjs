import { chromium } from "playwright";
// A browser check over a running stack: node check.mjs (playwright installed, or the mcr.microsoft.com/playwright image).

const base = process.env.BASE ?? "http://127.0.0.1:8080";
const shots = process.env.SHOTS ?? ".";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

await page.goto(base + "/");
await page.fill("#login-name", "root");
await page.fill("#login-password", "secret");
await page.click("button:has-text('log in')");
await page.waitForSelector("h1:has-text('Library')");
await page.waitForSelector("table tbody tr a");
await page.screenshot({ path: `${shots}/ui-library.png` });

const rows = await page.locator("table tbody tr").count();
console.log("library rows", rows);
await page.locator("a:has-text('detect · PP-DocLayoutV2')").first().click();
await page.waitForSelector(".sheet svg rect");
await page.waitForTimeout(800);
const boxes = await page.locator(".sheet svg rect").count();
console.log("boxes on page", boxes);
const tops = await page.locator(".sheet svg rect").evaluateAll((rs) => rs.map((r) => r.getBoundingClientRect().top));
const img = await page.locator(".sheet img").boundingBox();
console.log("topmost box within image:", ((Math.min(...tops) - img.y) / img.height).toFixed(3), "of the image height");
await page.click(".sheet svg rect >> nth=0");
await page.waitForSelector(".detail img");
await page.click("button:has-text('measure this page')");
await page.waitForSelector("text=Metrics on page", { timeout: 60000 });
await page.screenshot({ path: `${shots}/ui-viewer.png` });
console.log("metrics tables", await page.locator(".panel table").count());

const exported = await page.evaluate(async () => {
  const r = await fetch("/api/books/processed/e2e/runs/detect/PP-DocLayoutV2/export/html");
  const body = await r.text();
  return { status: r.status, type: r.headers.get("content-type"), anchors: (body.match(/ id="p\d{4}-b\d+"/g) || []).length, crops: (body.match(/data:image\/png;base64,/g) || []).length };
});
console.log("html export:", JSON.stringify(exported));
await page.fill("textarea[aria-label='corrected text']", "corrected by the check");
await page.click("button:has-text('correct')");
await page.waitForSelector("h1:has-text('.corrected')");
await page.waitForSelector("text=derived from");
console.log("corrections listed:", await page.locator("h2:has-text('Corrections')").count(), "· corrected mark:", await page.locator("td:has-text('✎')").count());
const fixed = await page.evaluate(async () => (await (await fetch("/api/books/processed/e2e/runs/detect/PP-DocLayoutV2.corrected/export/text")).text()).trim());
console.log("text export of the derived run:", JSON.stringify(fixed));
await page.click("button[aria-label='undo correction 0']");
await page.waitForSelector("h1:has-text('PP-DocLayoutV2')");
await page.waitForTimeout(500);
console.log("back on the base run:", !(await page.locator("h1").textContent()).includes(".corrected"));
await page.waitForSelector(".sheet svg rect");

const startTruth = page.locator("button:has-text('start truth')");
if (await startTruth.count()) await startTruth.click(); else await page.click("button:has-text('label')");
await page.waitForSelector(".sheet.label svg");
await page.click("button:has-text(\"take the run's boxes\")");
const taken = await page.locator(".side table tbody tr").count();
console.log("truth rows after taking the run:", taken, taken === boxes ? "(same as the run)" : "(differs from the run!)");
const sheet = await page.locator(".sheet.label svg").boundingBox();
await page.mouse.move(sheet.x + sheet.width * 0.2, sheet.y + sheet.height * 0.05);
await page.mouse.down();
await page.mouse.move(sheet.x + sheet.width * 0.6, sheet.y + sheet.height * 0.12, { steps: 5 });
await page.mouse.up();
console.log("truth rows after a drawn box:", await page.locator(".side table tbody tr").count());
await page.click("button:has-text('save layer')");
await page.waitForFunction(() => !document.querySelector("h2")?.textContent?.includes("unsaved"));
const truth = await page.evaluate(async () => (await fetch("/api/books/processed/e2e/truth/pages/0")).json());
console.log("truth page 0 now holds", truth.blocks.length, "blocks, layer by", truth.meta.author);
await page.screenshot({ path: `${shots}/ui-label.png` });
await page.click("button:has-text('done')");

await page.click("a:has-text('admin')");
await page.waitForFunction(() => (document.querySelector("#models-json").value || "").length > 2);
const models = await page.inputValue("#models-json");
console.log("registry has pp:", models.includes('"pp"'));
await page.screenshot({ path: `${shots}/ui-admin.png` });
console.log("page errors:", errors.length ? errors : "none");
await browser.close();
