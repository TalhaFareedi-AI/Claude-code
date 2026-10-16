// Real-browser check of the plan's screen rules and of full customization: 3 chips, settings groups with an
// Advanced fold, looks, themes, accent, size, saved to the account, long-answer fold, one-line steps, file cards.
// Usage: node scripts/look_ui_check.cjs   (server: UNLOCK_ALL=1 FAKE_DELAY=0 python backend/tests/demo_server.py)
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:8765';
const SHOTS = process.argv[3] || '/tmp/claude-0/shots';
const ok = []; const check = (n, v, x = '') => { ok.push(v); console.log(`${v ? 'PASS' : 'FAIL'}  ${n}${x ? '  ' + x : ''}`); };

(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  const errors = [];
  const ctx = await b.newContext({ viewport: { width: 1400, height: 860 } });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  const ready = (pg) => pg.waitForFunction(() => document.querySelector('#wallet-bal').textContent !== '–');
  const root = (pg) => pg.evaluate(() => { const r = document.documentElement, cs = getComputedStyle(document.body); return { theme: r.dataset.theme || 'auto', bg: cs.backgroundColor, scale: r.style.getPropertyValue('--scale'), width: r.style.getPropertyValue('--thread-w'), font: cs.fontFamily, btn: getComputedStyle(document.querySelector('#new-chat')).backgroundColor }; });
  const openLook = async (pg) => { if (await pg.locator('#settings').isHidden()) await pg.click('.chip:has-text("Settings")'); await pg.click('#tab-look-btn'); };
  const openMore = async (pg) => { const d = pg.locator('.tab-pane details.adv:has(summary:has-text("More ways to customize"))'); if (!(await d.evaluate((el) => el.open))) await d.locator('summary').click(); };
  const closeSheet = async (pg) => { await pg.click('#settings-close'); await pg.waitForFunction(() => document.querySelector('#settings').hidden); };
  await p.goto(BASE); await ready(p);

  // ---- 1. plan section 14: three chips, groups with plain names -------------------------
  const chips = await p.locator('#chips .chip').allInnerTexts();
  check('the main screen has exactly the three chips: Mode, Team, Tools', chips.length === 4 && /^Mode:/.test(chips[0]) && /^Team:/.test(chips[1]) && /^Tools:/.test(chips[2]) && /Settings/.test(chips[3]), chips.join(' | '));
  await p.click('#chips .chip:has-text("Tools")'); await p.waitForSelector('#settings:not([hidden])');
  check('a chip opens its own group', await p.locator('#tab-tools-btn[aria-selected="true"]').count() === 1);
  await p.click('#tab-models-btn');
  const advModels = p.locator('.tab-pane details.adv').first();
  check('Basic controls come first and the rest sits in a closed Advanced fold', await advModels.evaluate((el) => !el.open) && /Advanced/.test(await advModels.locator('summary').innerText()));
  check('using the default models is a single switch that starts on', await p.locator('#sw-model-defaults').isChecked() && await p.locator('select[aria-label="Understanding model"]').count() === 0);
  await p.locator('#sw-model-defaults').uncheck();
  check('turning it off shows the three model slots: understanding, enhancer, main',
    await p.locator('select[aria-label="Understanding model"]').count() === 1 && await p.locator('select[aria-label="Prompt enhancer model"]').count() === 1 && await p.locator('select[aria-label="Main model"]').count() === 1);
  await p.locator('#sw-model-defaults').check();
  check('answer style is a clear choice and Direct answers is the default',
    (await p.locator('[aria-label="Answer style"] button:has-text("Direct")').getAttribute('aria-pressed')) === 'true' && /tutor/i.test(await p.locator('[aria-label="Answer style"]').innerText()));
  await p.click('#tab-credits-btn');
  check('Credits has the per-message limit and the estimate switch', await p.locator('input[aria-label^="Most credits"]').count() === 1 && await p.locator('#sw-estimate').count() === 1);
  await closeSheet(p);

  // ---- 2. looks, themes, accent, size ----------------------------------------------------
  await openLook(p);
  const start = await root(p);
  await p.click('.look-card:has-text("Paper")');
  const paper = await root(p);
  check('a look repaints the page at once (Paper: warm background, serif, narrow)', paper.theme === 'sepia' && paper.bg !== start.bg && /Georgia|serif/i.test(paper.font) && paper.width === '660px', `${start.bg} -> ${paper.bg}`);
  await p.screenshot({ path: `${SHOTS}/70-look-paper.png` });
  await p.click('.look-card:has-text("Focus")');
  const focus = await root(p);
  check('Focus is dark and narrow', focus.theme === 'midnight' && focus.bg === 'rgb(0, 0, 0)');
  await p.click('.look-card:has-text("Big and clear")');
  const big = await root(p);
  check('Big and clear is high contrast with large text', big.theme === 'contrast' && parseFloat(big.scale) >= 1.2);
  await p.click('.look-card:has-text("Calm")');
  const accents = [];
  for (const [theme, label, k] of [['sepia', 'Paper', 'rose'], ['midnight', 'Midnight', 'violet'], ['light', 'Light', 'blue']]) {
    await p.click(`.theme-opt:has-text("${label}")`); await p.click(`.swatch[data-k="${k}"]`);
    accents.push((await root(p)).btn);
  }
  check('the accent color wins in every theme (rose, violet, blue)', accents[0] === 'rgb(194, 65, 93)' && accents[1] !== accents[2] && accents[2] === 'rgb(47, 111, 209)', accents.join(' / '));
  await p.locator('input[type=color]').evaluate((el) => { el.value = '#d6336c'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  check('any color can be picked', (await root(p)).btn === 'rgb(214, 51, 108)');
  const sz = p.locator('input[type=range][aria-label="Text size"]');
  await sz.evaluate((el) => { el.value = '130'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  check('text size is a slider that scales the whole page', (await root(p)).scale === '1.3' && await p.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize) > 20));
  await sz.evaluate((el) => { el.value = '100'; el.dispatchEvent(new Event('input', { bubbles: true })); });

  // ---- 3. the deeper options -------------------------------------------------------------
  await openMore(p);
  await p.locator('[aria-label="Chat width"] button:has-text("Wide")').click();
  check('chat width changes how wide the conversation is', (await root(p)).width === '1040px');
  await p.locator('[aria-label="Corners"] button:has-text("Square")').click();
  check('corner style changes every pill and card', await p.evaluate(() => document.documentElement.dataset.round === 'sharp' && parseFloat(getComputedStyle(document.querySelector('.chip')).borderTopLeftRadius) <= 8));
  await p.locator('[aria-label="Corners"] button:has-text("Soft")').click();
  await p.locator('input[aria-label="Show Effort"]').check();
  await p.locator('input[aria-label="Show Team"]').uncheck();
  const chips2 = (await p.locator('#chips .chip').allInnerTexts()).join(' | ');
  check('the buttons above the message box can be chosen', /Effort:/.test(chips2) && !/Team:/.test(chips2), chips2);
  await p.locator('input[aria-label="Show My activity"]').uncheck();
  check('sidebar shortcuts can be hidden', await p.locator('#open-activity').isHidden() && await p.locator('#open-profile').isVisible());
  await p.locator('input[aria-label="Show Team"]').check(); await p.locator('input[aria-label="Show Effort"]').uncheck(); await p.locator('input[aria-label="Show My activity"]').check();
  await p.screenshot({ path: `${SHOTS}/71-look-more.png` });
  await p.waitForTimeout(700);

  // ---- 4. saved on the account: wipe this browser, the look comes back ----------------------
  const server = await p.evaluate(async () => (await (await fetch('/api/bootstrap')).json()).ui_prefs);
  check('the look is saved on the server', server.accent === '#d6336c' && server.width === 'wide' && server.theme === 'light', JSON.stringify(server).slice(0, 90));
  await p.evaluate(() => localStorage.clear()); await p.reload(); await ready(p);
  const back = await root(p);
  check('after wiping the browser the same look comes back from the account', back.theme === 'light' && back.btn === 'rgb(214, 51, 108)' && back.width === '1040px');
  await openLook(p); await p.click('button:has-text("Reset the look")');
  const reset = await root(p);
  check('Reset the look returns to the defaults', reset.theme === 'auto' && reset.scale === '1' && reset.width === '820px');
  await closeSheet(p);

  // ---- 5. chat parts from the plan ---------------------------------------------------------
  await p.fill('#composer-text', 'give me a very long answer about plants'); await p.click('#send-btn');
  await p.waitForFunction(() => document.querySelectorAll('.msg-foot').length >= 1, null, { timeout: 25000 });
  await p.waitForSelector('.answer.folded', { timeout: 5000 }).catch(() => {});
  check('a long answer folds with Show more', await p.locator('.answer.folded').count() === 1 && await p.locator('.fold-toggle:has-text("Show more")').count() === 1);
  await p.screenshot({ path: `${SHOTS}/72-folded.png` });
  await p.click('.fold-toggle');
  check('Show more opens the whole answer, Show less folds it again', await p.locator('.answer.folded').count() === 0 && await p.locator('.fold-toggle:has-text("Show less")').count() === 1
    && /Point 45/.test(await p.locator('.msg.assistant .answer').last().innerText()));
  check('a finished run is one line such as "3 steps, 1 credit"', /\d+ steps?, \d+ credits?/.test(await p.locator('.run-title').last().innerText() || ''), await p.locator('.run-title').last().innerText());
  await openLook(p); await openMore(p);
  await p.locator('#sw-fold').uncheck(); await closeSheet(p);
  check('the fold can be switched off', await p.locator('.answer.folded').count() === 0 && await p.locator('.fold-toggle').count() === 0);
  const cards = await p.evaluate(async () => {
    const { fileCards } = await import('/js/files.js');
    const one = fileCards([{ id: 'a', name: 'plan.pptx', kind: 'pptx', size: 52000, version: 2 }], { onOpen() {} });
    const many = fileCards([{ id: 'a', name: 'plan.pptx', kind: 'pptx', size: 52000 }, { id: 'b', name: 'notes.docx', kind: 'docx', size: 9000 }, { id: 'c', name: 'chart.png', kind: 'png', size: 120000 }], { onOpen() {} });
    document.body.append(one, many);
    const out = { one: one.className, summary: many.querySelector('summary').textContent, rows: many.querySelectorAll('.file-row').length, meta: one.querySelector('.meta').textContent, btns: [...many.querySelectorAll('button')].map((x) => x.textContent) };
    one.remove(); many.remove(); return out;
  });
  check('several files group into one "Files (3)" card with Open and Download', /Files \(3\)/.test(cards.summary) && cards.rows === 3 && cards.btns.filter((x) => x === 'Open').length === 3 && cards.btns.filter((x) => x === 'Download').length === 3);
  check('a file card shows type, size and version', /PPTX · 51 KB · version 2/.test(cards.meta), cards.meta);

  // ---- 6. behavior switches ---------------------------------------------------------------
  await openLook(p); await openMore(p);
  await p.locator('#sw-enter').uncheck(); await closeSheet(p);
  const before = await p.locator('.msg.user').count();
  await p.fill('#composer-text', 'hello there'); await p.press('#composer-text', 'Enter');
  await p.waitForTimeout(400);
  check('with Enter-to-send off, plain Enter makes a new line and does not send', await p.locator('.msg.user').count() === before && (await p.inputValue('#composer-text')) === 'hello there\n');
  await p.press('#composer-text', 'Control+Enter');
  await p.waitForFunction((n) => document.querySelectorAll('.msg.user').length > n, before, { timeout: 10000 });
  check('Ctrl+Enter sends instead', await p.locator('.msg.user').count() === before + 1);
  await p.waitForFunction(() => !document.querySelector('.run.working'), null, { timeout: 20000 });
  await openLook(p); await openMore(p); await p.locator('#sw-enter').check(); await closeSheet(p);

  // ---- 7. a phone ----------------------------------------------------------------------------
  const m = await (await b.newContext({ viewport: { width: 390, height: 780 }, isMobile: true, hasTouch: true })).newPage();
  m.on('pageerror', (e) => errors.push('phone pageerror: ' + e.message));
  await m.goto(BASE); await ready(m);
  await m.click('.chip:has-text("Settings")'); await m.click('#tab-look-btn');
  await m.click('.look-card:has-text("Paper")');
  await openMore(m);
  check('phone: the look page fits the screen', await m.evaluate(() => { const l = document.querySelector('.tab-pane'); return l.scrollWidth <= l.clientWidth + 1 && document.documentElement.scrollWidth <= innerWidth; }));
  await m.screenshot({ path: `${SHOTS}/73-phone-look.png` });

  check('no browser errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  await b.close();
  const bad = ok.filter((x) => !x).length;
  console.log(bad ? `\n${bad} FAILED` : `\nall ${ok.length} look and layout checks passed`);
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error('crashed:', e.message.split('\n').slice(0, 6).join('\n')); process.exit(2); });
