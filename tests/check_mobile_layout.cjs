// Optional browser regression: NODE_PATH must include a Playwright installation.
// Run with node tests/check_mobile_layout.cjs after installing Chromium and WebKit.
// BOOKKEEPING_TEST_CHROMIUM_EXECUTABLE can select an installed Edge/Chrome binary.
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");
const { chromium, webkit } = require("playwright");

const staticRoot = path.resolve(__dirname, "../bookkeeping/web_static");
const contentTypes = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png" };
const fixture = {
  settings: { monthly_jpy_budget_minor: "30000" },
  balanceSheet: { net_assets: { JPY: "42000", CNY: "120000" } },
  profit: {
    start: "2026-10-15", through: "2026-10-23",
    jpy_equivalent: {
      expense_minor: "8200", income_minor: "31000", missing_conversion_count: "0",
      categories: { "娱乐": "4100", "餐饮": "2250", "LongUnbrokenCategoryNameForLayoutRegression": "1225", "日用品": "625" },
    },
  },
  transactions: [{
    id: "layout-entry", kind: "expense", description: "Layout regression with a long transaction description",
    account_name: "Synthetic layout account", category_name: "餐饮", amount_minor: "1533", currency: "JPY", occurred_on: "2026-10-22",
  }],
};

function measure() {
  const client = document.documentElement.clientWidth;
  const rect = selector => {
    const box = document.querySelector(selector).getBoundingClientRect();
    return { x: box.x, right: box.right, width: box.width };
  };
  const overflow = [...document.body.querySelectorAll("*")].filter(node => {
    const closedDetails = node.closest("details:not([open])");
    if (closedDetails && !closedDetails.querySelector("summary")?.contains(node)) return false;
    const box = node.getBoundingClientRect();
    return box.width > 0 && (box.right > client + 1 || box.x < -1);
  }).slice(0, 5).map(node => node.id || node.getAttribute("class") || node.tagName);
  return { client, scroll: document.documentElement.scrollWidth, header: rect(".topbar"), main: rect("main"), overflow };
}

function assertFits(layout, label) {
  assert.ok(layout.scroll <= layout.client, `${label}: page width ${layout.scroll} exceeds screen ${layout.client}`);
  assert.ok(Math.abs(layout.header.width - layout.client) <= 1, `${label}: topbar does not fill the screen`);
  assert.ok(layout.main.right <= layout.client + 1, `${label}: main extends beyond the screen`);
  assert.deepEqual(layout.overflow, [], `${label}: visible content extends beyond the screen`);
}

async function run() {
  // This server only serves source assets. It cannot read or write user ledgers.
  const server = http.createServer(async (request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    const file = path.resolve(staticRoot, pathname === "/" ? "index.html" : "." + pathname);
    if (!file.startsWith(staticRoot + path.sep) || pathname.startsWith("/api/")) {
      response.writeHead(401, { "Content-Type": "application/json" });
      response.end('{"error":"Synthetic layout check"}');
      return;
    }
    try {
      const data = await fs.readFile(file);
      response.writeHead(200, { "Content-Type": (contentTypes[path.extname(file)] || "application/octet-stream") + "; charset=utf-8", "Cache-Control": "no-store" });
      response.end(data);
    } catch {
      response.writeHead(404).end();
    }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let checks = 0;
  try {
    for (const engine of [webkit, chromium]) {
      const options = { headless: true };
      if (engine === chromium && process.env.BOOKKEEPING_TEST_CHROMIUM_EXECUTABLE) options.executablePath = process.env.BOOKKEEPING_TEST_CHROMIUM_EXECUTABLE;
      const browser = await engine.launch(options);
      try {
        const context = await browser.newContext({ viewport: { width: 402, height: 874 }, isMobile: true, hasTouch: true, serviceWorkers: "block", reducedMotion: "reduce" });
        const page = await context.newPage();
        await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: "networkidle" });
        await page.evaluate(async () => { await appInitialization; });
        for (const width of [320, 375, 393, 402, 430, 768, 874, 1280]) {
          await page.setViewportSize({ width, height: width === 874 ? 402 : 874 });
          for (const language of ["zh-CN", "ja-JP", "en-US"]) {
            for (const theme of ["light", "dark"]) {
              const label = `${engine.name()} ${width}px ${language} ${theme}`;
              await page.evaluate(({ language, theme }) => {
                currentLanguage = language;
                baseApplyLanguage();
                document.documentElement.dataset.theme = theme;
                baseShowLoggedOut();
              }, { language, theme });
              assertFits(await page.evaluate(measure), label + " signed out");
              await page.evaluate(data => {
                currentUser = { id: "synthetic-layout-user", username: "Synthetic user" };
                workspace = data;
                serverReachable = true;
                baseShowLoggedIn();
                selectedPage = "home";
                renderNavigation();
                renderDashboard();
              }, fixture);
              assertFits(await page.evaluate(measure), label + " signed in");
              // Descendant bounds catch clipping-only fixes that hide wide cards.
              const cards = await page.evaluate(() => {
                const main = document.querySelector("main"), style = getComputedStyle(main);
                const left = main.getBoundingClientRect().left + parseFloat(style.paddingLeft);
                const right = main.getBoundingClientRect().right - parseFloat(style.paddingRight);
                return [...document.querySelector("#page-home").children].every(node => {
                  const box = node.getBoundingClientRect();
                  return box.x >= left - 1 && box.right <= right + 1;
                });
              });
              assert.ok(cards, label + ": dashboard cards extend beyond their container");
              checks++;
            }
          }
        }
      } finally {
        await browser.close();
      }
    }
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
  console.log(`PASS: ${checks} browser, viewport, language and theme combinations before and after sign-in.`);
}

run().catch(error => { console.error(error); process.exitCode = 1; });
