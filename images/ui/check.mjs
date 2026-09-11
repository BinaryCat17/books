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

await page.click("a:has-text('admin')");
await page.waitForFunction(() => (document.querySelector("#models-json").value || "").length > 2);
const models = await page.inputValue("#models-json");
console.log("registry has pp:", models.includes('"pp"'));
await page.screenshot({ path: `${shots}/ui-admin.png` });
console.log("page errors:", errors.length ? errors : "none");
await browser.close();
