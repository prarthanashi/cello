// Optional browser journey test. Needs Playwright + Chromium; see README "End-to-end check".
const { chromium } = require("playwright");
const assert = require("assert");
const BASE = process.env.BASE_URL || "http://127.0.0.1:4173";
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  await page.goto(BASE + "/");
  await page.waitForSelector("text=Build your business profile");
  assert(await page.locator("text=not a government website").count() >= 1, "footer notice");
  assert(await page.locator("text=Backend connected").count(), "status pill");
  assert(await page.locator("text=AI not configured").count(), "AI pill");

  // E1: empty submit -> field errors, entered values preserved
  await page.selectOption("#f-state_ut", "Kerala");
  await page.fill("#f-district", "Kochi");
  await page.click("text=Find relevant schemes");
  await page.waitForSelector("#err-business_type:not(:empty)");
  assert.equal(await page.inputValue("#f-district"), "Kochi", "values preserved");
  assert.equal(await page.inputValue("#f-state_ut"), "Kerala");
  assert(await page.locator("text=Please complete the highlighted fields").isVisible());
  await page.screenshot({ path: (process.env.SHOT_DIR || ".") + "/01-validation.png" });

  // sample profile -> matches
  await page.click("text=Use sample profile");
  await page.waitForSelector("#f-state_ut");
  assert.equal(await page.inputValue("#f-state_ut"), "Tamil Nadu");
  await page.click("text=Find relevant schemes");
  await page.waitForSelector("text=Your matches");
  const titles = await page.locator(".scheme-card:not(.unlikely .scheme-card) h3").allTextContents();
  console.log("cards:", titles);
  assert(titles.some((t) => t.includes("PMEGP")) && titles.some((t) => t.includes("NEEDS")) && titles.some((t) => t.includes("MUDRA")));
  assert(!titles.some((t) => t.includes("SVANidhi")), "SVANidhi must not be a likely match");
  assert(await page.locator("text=Schemes unlikely to qualify (1)").count());
  assert(await page.locator("text=Last verified").count() >= 3);
  await page.screenshot({ path: (process.env.SHOT_DIR || ".") + "/02-matches.png", fullPage: true });

  // filter
  await page.selectOption(".filters label:has-text('Scheme type') select", "state_ut");
  assert.equal(await page.locator(".scheme-card:not(.unlikely .scheme-card) h3").count(), 1);
  await page.click("text=Reset filters");
  assert(await page.locator(".scheme-card:not(.unlikely .scheme-card) h3").count() >= 3);

  // detail
  await page.locator("article:has-text('NEEDS') button:has-text('View details')").click();
  await page.waitForSelector("#documents");
  for (const id of ["overview", "qualify", "exclude", "benefits", "documents", "apply", "source", "assistant"]) assert(await page.locator("#" + id).count(), id);
  assert(await page.locator("a.official[target=_blank][rel*=noopener]").count() >= 1);
  assert(await page.locator(".req.conditional").count() && await page.locator(".req.confirm").count());
  assert(await page.locator("text=Confirm with official source").count());
  await page.locator(".doc input[type=checkbox]").first().check();
  await page.screenshot({ path: (process.env.SHOT_DIR || ".") + "/03-detail.png", fullPage: true });

  // assistant, demo mode
  await page.click("text=Which documents are listed?");
  await page.waitForSelector(".msg.bot.excerpts");
  const bot = await page.locator(".msg.bot.excerpts").innerText();
  assert(bot.includes("AI answers are not configured yet; scheme matching and official links remain available."));
  assert(bot.includes("not AI-generated advice"));
  assert(await page.locator(".cite a.official").count() >= 1);
  await page.fill(".ask-row textarea", "Who won the cricket world cup?");
  await page.click(".ask-row button");
  await page.waitForSelector(".msg.bot.no_context");
  assert((await page.locator(".msg.bot.no_context").innerText()).includes("couldn’t verify"));
  await page.fill(".ask-row textarea", "   ");
  await page.click(".ask-row button");
  await page.waitForSelector("text=Enter a question of up to 2,000 characters.");
  await page.screenshot({ path: (process.env.SHOT_DIR || ".") + "/04-assistant.png", fullPage: false });

  // checklist copy + tick persisted across navigation
  await page.goBack(); await page.waitForSelector("text=Your matches");
  await page.locator("article:has-text('NEEDS') button:has-text('View details')").click();
  await page.waitForSelector("#documents");
  assert(await page.locator(".doc input[type=checkbox]").first().isChecked(), "tick persisted in session");

  // unknown scheme + backend down handling
  await page.goto(BASE + "/#/scheme/does-not-exist");
  await page.waitForSelector("text=couldn’t find that scheme");
  console.log("console errors:", errors);
  assert.deepEqual(errors.filter((e) => !/Failed to load resource: the server responded with a status of (400|404|503)/.test(e)), [], "unexpected script/console errors");
  await browser.close();
  console.log("E2E OK");
})().catch((e) => { console.error("E2E FAILED:", e.message); process.exit(1); });
