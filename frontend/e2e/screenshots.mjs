// Captures every key screen of the running app (uvicorn on :8000, frontend/dist built).
// Usage (from frontend/): node e2e/screenshots.mjs <out-dir>
import { chromium } from "@playwright/test";
import fs from "fs";

const OUT = process.argv[2] ?? "../docs/screenshots";
fs.mkdirSync(OUT, { recursive: true });
const BASE = "http://127.0.0.1:8000";
const TOKEN = fs.readFileSync("../.env", "utf8").match(/^ADMIN_TOKEN=(.+)$/m)[1].trim();
const browser = await chromium.launch();
const errors = [];
const watch = (page, tag) => {
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${tag}: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`${tag}: ${String(e)}`));
};
const settle = (page, ms = 1500) => page.waitForTimeout(ms);

// traveller, desktop
const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
watch(page, "desktop");
await page.goto(`${BASE}/`);
await page.waitForSelector("select option", { state: "attached" });
await settle(page);
await page.screenshot({ path: `${OUT}/01-home.png`, fullPage: true });
await page.getByRole("button", { name: /Show rooms/ }).click();
await page.waitForSelector("ul.ledger li h3");
await settle(page);
await page.screenshot({ path: `${OUT}/02-results.png`, fullPage: true });
await page.locator("ul.ledger li a").first().click();
await page.waitForSelector("[data-testid=pass-no]");
await settle(page, 900);
await page.screenshot({ path: `${OUT}/03-pass-en.png`, fullPage: true });
await page.getByRole("button", { name: "हिन्दी" }).click();
await settle(page, 1200);
await page.screenshot({ path: `${OUT}/04-pass-hi.png`, fullPage: true });
await page.getByRole("button", { name: "English" }).click();

// traveller, phone
const phone = await browser.newPage({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2 });
watch(phone, "phone");
await phone.goto(`${BASE}/`);
await phone.waitForSelector("select option", { state: "attached" });
await settle(phone);
await phone.screenshot({ path: `${OUT}/05-home-375.png`, fullPage: true });
await phone.getByRole("button", { name: /Show rooms/ }).click();
await phone.waitForSelector("ul.ledger li h3");
await settle(phone);
await phone.locator("ul.ledger li a").first().click();
await phone.waitForSelector("[data-testid=pass-no]");
await settle(phone, 900);
await phone.screenshot({ path: `${OUT}/06-pass-375.png`, fullPage: true });
const overflow = await phone.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
if (overflow) errors.push("phone: horizontal overflow on price pass");

// desk
const desk = await browser.newPage({ viewport: { width: 1280, height: 860 } });
watch(desk, "desk");
await desk.goto(`${BASE}/desk`);
await settle(desk);
await desk.screenshot({ path: `${OUT}/07-desk-signin.png` });
await desk.fill("input[type=password]", TOKEN);
await desk.getByRole("button", { name: /Open the desk/ }).click();
await desk.waitForSelector("svg[role=img]");
await settle(desk, 1200);
await desk.screenshot({ path: `${OUT}/08-desk-curve.png`, fullPage: true });
const curveSvg = desk.locator("svg[role=img]").first();
await curveSvg.scrollIntoViewIfNeeded();
await settle(desk, 400);
const box = await curveSvg.boundingBox();
await desk.mouse.click(box.x + box.width * 0.55, box.y + box.height * 0.5);
await desk.waitForSelector("[role=dialog]");
await settle(desk, 1200);
await desk.screenshot({ path: `${OUT}/09-drawer.png` });
await desk.keyboard.press("Escape");
for (const [i, s] of ["approvals", "controls", "signals", "simulator", "metrics", "audit", "proof"].entries()) {
  await desk.locator(`nav[aria-label=Desk] a[href^="/desk/${s}"]`).click();
  if (s === "proof") await desk.waitForSelector("main ol li", { timeout: 120000 });
  await settle(desk, 1500);
  await desk.screenshot({ path: `${OUT}/${String(10 + i).padStart(2, "0")}-desk-${s}.png`, fullPage: true });
}
console.log("errors:", JSON.stringify(errors.slice(0, 20)));
await browser.close();
