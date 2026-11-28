// The picture of ade web's Docs page for step 7 of the ui-tour drill (story D5), drawn by Playwright's Chromium at
// 1280x720: node shot.cjs <url> <out.png> <out.txt> <out.html> [one-time code]. The page's text goes to out.txt and its
// HTML (alt, title and links too) to out.html, for the drill's leak scan. It fails (exit 3) when no diagram was drawn: the step's caption says "diagrams and all".
const fs = require('fs');
const { chromium } = require('playwright');
(async () => {
  const [url, png, txt, html, code] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.goto(url, { waitUntil: 'networkidle' });
  const input = await page.$('#gate #gi');   // ade web's sign-in field (the code), nothing else on the page
  if (input && code) { await input.fill(code); await input.press('Enter'); await page.waitForLoadState('networkidle'); }
  let drawn = true;
  try { await page.waitForSelector('svg[id^="mermaid"], .mermaid svg, pre.mermaid svg', { timeout: 15000 }); } catch (e) { drawn = false; }
  await page.screenshot({ path: png });
  fs.writeFileSync(txt, await page.innerText('body'));
  fs.writeFileSync(html, await page.content());
  await browser.close();
  if (!drawn) { console.error('the Docs page drew no diagram'); process.exit(3); }
})().catch((e) => { console.error(e.message); process.exit(1); });
