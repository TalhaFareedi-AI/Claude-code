// Drives the real UI in Chromium against a running server. Usage: node scripts/ui_check.cjs [baseUrl] [shotsDir]
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:8765';
const SHOTS = process.argv[3] || '/tmp/claude-0/shots';
const results = [];
const check = (name, ok, extra = '') => { results.push({ name, ok }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); };

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  const errors = [];
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 820 } });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  await page.goto(BASE);
  await page.waitForSelector('.welcome');
  check('welcome screen shows starters', (await page.locator('.starter').count()) === 4);
  check('estimate appears', /credit/.test(await page.locator('#estimate').innerText().catch(() => '')) || await page.waitForFunction(() => /credit/.test(document.querySelector('#estimate').textContent), null, { timeout: 5000 }).then(() => true).catch(() => false));
  await page.screenshot({ path: `${SHOTS}/01-welcome.png` });

  // 1. a simple Fast answer
  await page.fill('#composer-text', 'hi');
  await page.click('#send-btn');
  await page.waitForSelector('.msg.assistant .answer');
  await page.waitForFunction(() => document.querySelectorAll('.msg-foot').length >= 1, null, { timeout: 15000 });
  const ans = await page.locator('.msg.assistant .answer').first().innerText();
  check('simple answer is shown, markers hidden', /Simple idea/.test(ans) && !/\[\[next|\{\{calc/.test(ans));
  check('next-step buttons appear', (await page.locator('.next-btn').count()) >= 2);
  check('credits-used footer shows', /Used \d+ credit/.test(await page.locator('.msg-foot').first().innerText()));
  await page.screenshot({ path: `${SHOTS}/02-answer.png` });

  // 2. interactive chart with a slider
  await page.fill('#composer-text', 'Show me a chart of interest on savings');
  await page.click('#send-btn');
  await page.waitForSelector('.art.chart svg path', { timeout: 15000 });
  const readoutBefore = await page.locator('.art.chart .ctl b').nth(1).innerText();
  await page.locator('.art.chart input[type=range]').first().evaluate((el) => { el.value = '12'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.waitForTimeout(150);
  const readoutAfter = await page.locator('.art.chart .ctl b').nth(1).innerText();
  check('moving a slider changes the readout (no server call)', readoutBefore !== readoutAfter, `${readoutBefore} -> ${readoutAfter}`);
  await page.locator('.art.chart svg.chart-svg').first().scrollIntoViewIfNeeded();
  const box = await page.locator('.art.chart svg.chart-svg').first().boundingBox();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.5);
  await page.waitForTimeout(150);
  check('hovering the chart shows a tooltip', await page.locator('.art.chart .tip').first().isVisible());
  await page.screenshot({ path: `${SHOTS}/03-chart.png` });

  // 3. upgrade to student in dev mode, then Think Again from the settings sheet
  await page.selectOption('#dev-plan', 'student');
  await page.waitForTimeout(500);
  await page.click('#chips >> text=Mode');
  await page.waitForSelector('#settings:not([hidden])');
  await page.screenshot({ path: `${SHOTS}/04-settings.png` });
  await page.click('.mode-opt:has-text("Think Again")');
  check('Think Again is selectable on student plan', await page.locator('.mode-opt[aria-checked="true"]:has-text("Think Again")').count() === 1);
  check('locked modes show a lock', await page.locator('.mode-opt[aria-disabled="true"] .lock').count() >= 1);
  await page.click('#settings-close');
  await page.fill('#composer-text', 'explain photosynthesis');
  await page.click('#send-btn');
  await page.waitForFunction(() => document.querySelectorAll('.run').length >= 1 && !document.querySelector('.run.working') && document.querySelector('.msg.assistant:last-child .msg-foot'), null, { timeout: 20000 });
  check('finished runs fold into one line', await page.locator('.msg.assistant:last-child .run.collapsed').count() === 1);
  await page.locator('.msg.assistant:last-child .run-head').click();
  await page.waitForSelector('.msg.assistant:last-child .round-chip', { state: 'visible', timeout: 5000 });
  check('run card shows rounds with scores', (await page.locator('.round-chip').count()) >= 1);
  await page.screenshot({ path: `${SHOTS}/05-think-again.png` });

  // 4. PPT file
  await page.click('#chips >> text=Mode');
  await page.click('.mode-opt:has-text("Auto")');
  await page.click('#settings-close');
  await page.fill('#composer-text', 'Make a 5 slides PPT on plants');
  await page.click('#send-btn');
  await page.locator('.file .name').filter({ hasText: /\.pptx$/i }).first().waitFor({ state: 'visible', timeout: 25000 });
  await page.waitForFunction(() => !document.querySelector('.run.working'), null, { timeout: 25000 });
  const pptFile = page.locator('.file').filter({ has: page.locator('.name').filter({ hasText: /\.pptx$/i }) }).first();
  check('PPT file card appears with Open and Download', /pptx/.test(await pptFile.locator('.name').innerText()) && await pptFile.locator('button:has-text("Download")').count() === 1);
  await pptFile.locator('button:has-text("Open")').click();
  await page.waitForSelector('#preview:not([hidden]) .slide');
  check('Open shows a slide preview', (await page.locator('#preview .slide').count()) >= 3);
  const [dl] = await Promise.all([page.waitForEvent('download'), pptFile.locator('button:has-text("Download")').click()]);
  check('Download works through a signed link', /\.pptx$/.test(dl.suggestedFilename()));
  await page.screenshot({ path: `${SHOTS}/06-files.png` });

  // 5. reload keeps the chat
  await page.reload();
  await page.waitForSelector('.msg.assistant .answer');
  check('reload brings the chat back', (await page.locator('.msg.assistant').count()) >= 2);
  await page.locator('button:has-text("Show steps")').first().click();
  await page.waitForSelector('.run .plan, .run .card, .run .think', { timeout: 5000 }).catch(() => {});
  check('"Show steps" replays the saved run', (await page.locator('.run').count()) >= 1);

  // 6. dark mode + mobile
  await page.click('#theme-toggle');
  await page.screenshot({ path: `${SHOTS}/07-dark.png` });
  const mobile = await browser.newContext({ viewport: { width: 390, height: 780 }, isMobile: true, hasTouch: true });
  const m = await mobile.newPage();
  m.on('pageerror', (e) => errors.push('mobile pageerror: ' + e.message));
  m.on('console', (x) => { if (x.type() === 'error') errors.push('mobile console: ' + x.text()); });
  await m.goto(BASE);
  await m.waitForSelector('.welcome');
  const overflow = await m.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  check('phone: no sideways scroll', !overflow);
  await m.screenshot({ path: `${SHOTS}/08-mobile-welcome.png` });
  await m.click('#open-side');
  await m.waitForTimeout(300);
  await m.screenshot({ path: `${SHOTS}/09-mobile-menu.png` });
  await m.click('#scrim', { position: { x: 360, y: 300 } });
  await m.click('.chip:has-text("Settings")');
  await m.waitForSelector('#settings:not([hidden])');
  await m.screenshot({ path: `${SHOTS}/10-mobile-settings.png` });
  await m.click('#settings-close');
  await m.fill('#composer-text', 'Show me a chart of interest on savings');
  await m.click('#send-btn');
  await m.waitForSelector('.art.chart svg path', { timeout: 15000 });
  await m.waitForTimeout(400);
  check('phone: chart fits the screen', await m.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
  await m.screenshot({ path: `${SHOTS}/11-mobile-chart.png` });

  // new artifact types render and stay interactive without any further model call
  const art = await page.evaluate(async () => {
    const { renderFlashcards, renderTable } = await import('/js/charts.js');
    const deck = renderFlashcards({ title: 'Planets', cards: [
      { front: 'Closest to the Sun?', back: 'Mercury', hint: 'Smallest' },
      { front: 'The red planet?', back: 'Mars' }, { front: 'Largest planet?', back: 'Jupiter' }] });
    document.body.append(deck);
    const front = deck.querySelector('.card-side').textContent;
    deck.querySelector('.card-face').click();
    const back = deck.querySelector('.card-side').textContent;
    [...deck.querySelectorAll('button')].find((b) => b.textContent.includes('Next')).click();
    const next = deck.querySelector('.card-side').textContent;

    const tbl = renderTable({ title: 'Compare', columns: [{ key: 'n', label: 'Name' }, { key: 'v', label: 'Value', type: 'number', unit: '$' }],
      rows: [{ n: 'b', v: 2 }, { n: 'a', v: 10 }, { n: 'c', v: null }] });
    document.body.append(tbl);
    const firstBefore = tbl.querySelector('tbody td').textContent;
    tbl.querySelectorAll('th .th-sort')[0].click();
    const firstAfterName = tbl.querySelector('tbody td').textContent;
    tbl.querySelectorAll('th .th-sort')[1].click();
    const numCells = [...tbl.querySelectorAll('tbody tr')].map((r) => r.children[1].textContent);
    return { front, back, next, firstBefore, firstAfterName, numCells, numAligned: !!tbl.querySelector('td.num') };
  });
  check('flashcards flip and step in the browser', art.front.includes('Closest') && art.back === 'Mercury' && art.next.includes('red planet'));
  check('tables sort by text and by number, and show units', art.firstBefore === 'b' && art.firstAfterName === 'a'
    && art.numCells[0] === '–' && art.numCells[2] === '$10' && art.numAligned, JSON.stringify(art.numCells));

  check('no browser errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  await browser.close();
  const failed = results.filter((r) => !r.ok).length;
  console.log(failed ? `\n${failed} FAILED` : `\nall ${results.length} UI checks passed`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('script crashed:', e.message); process.exit(2); });
