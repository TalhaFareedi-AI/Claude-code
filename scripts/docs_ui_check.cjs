// Real-browser check of documents, decks, generated pictures, the reader panel and response length.
// Usage: node scripts/docs_ui_check.cjs   (server: UNLOCK_ALL=1 FAKE_DELAY=0 python backend/tests/demo_server.py)
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:8765';
const SHOTS = process.argv[3] || '/tmp/claude-0/shots';
const ok = []; const check = (n, v, x = '') => { ok.push(v); console.log(`${v ? 'PASS' : 'FAIL'}  ${n}${x ? '  ' + x : ''}`); };

(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  const errors = [];
  const ctx = await b.newContext({ viewport: { width: 1500, height: 900 } });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  p.on('dialog', (d) => d.accept());  // the delete confirmation
  await p.goto(BASE);
  await p.waitForFunction(() => document.querySelector('#wallet-bal').textContent !== '–');
  const openSettings = async (tab) => {
    if (await p.locator('#settings').isHidden()) await p.click('.chip:has-text("Settings")');
    await p.waitForSelector('#settings:not([hidden])');
    await p.click(`#tab-${tab}-btn`);
  };
  const closeSettings = async () => { await p.click('#settings-close'); await p.waitForFunction(() => document.querySelector('#settings').hidden); };
  const ask = async (text) => {
    const before = await p.locator('.msg.assistant').count();
    await p.fill('#composer-text', text);
    await p.click('#send-btn');
    await p.waitForFunction((n) => document.querySelectorAll('.msg-foot').length > n, before, { timeout: 25000 });
  };

  // ---- 1. a document arrives as a card, not as a wall of markdown ----------------------
  await ask('write a document that teaches me how AI learns');
  await p.waitForSelector('.art.doc-art', { timeout: 20000 });
  const card = p.locator('.art.doc-art').first();
  check('a document comes back as a card with its title', /AI Learning Guide/.test(await card.innerText()));
  check('the card says how long it is and where it was saved', /words · saved as .+\.md/.test(await card.innerText()));
  check('the card shows a real preview, not raw markdown', (await card.locator('.doc-preview h1, .doc-preview h2').count()) >= 1
    && !/```|^#\s/m.test(await card.locator('.doc-preview').innerText()));
  await p.screenshot({ path: `${SHOTS}/50-doc-card.png` });

  // ---- 2. Open puts it in the workspace panel on the right ----------------------------
  await card.locator('.doc-more').click();
  await p.waitForSelector('#files-panel:not([hidden])', { timeout: 8000 });
  await p.waitForSelector('#preview .doc-read', { timeout: 8000 });
  check('Open shows the workspace panel with the document in it',
    await p.locator('#files-panel').isVisible() && /AI Learning Guide/.test(await p.locator('#preview').innerText()));
  check('the document is also listed as a file in the workspace', (await p.locator('#file-list .file').count()) >= 1
    && /\.md$/.test(await p.locator('#file-list .file .name').first().innerText()));
  check('the storage meter is filled in', /of .+ used/.test(await p.locator('#ws-usage').innerText()));
  await p.screenshot({ path: `${SHOTS}/51-doc-reader.png` });

  // ---- 3. a deck ----------------------------------------------------------------------
  await ask('make me a deck about the water cycle');
  await p.waitForSelector('.art.doc-art:has(.doc-ico:text("📊"))', { timeout: 20000 });
  const deck = p.locator('.art.doc-art').last();
  check('a deck comes back as its own card counted in slides', /slides · saved as/.test(await deck.innerText()));
  await deck.locator('.doc-more').click();
  await p.waitForSelector('#preview .slide-page', { timeout: 8000 });
  check('the reader splits the deck into numbered slides', (await p.locator('#preview .slide-page').count()) >= 3
    && /Slide 1/.test(await p.locator('#preview').innerText()));
  await p.screenshot({ path: `${SHOTS}/52-deck-reader.png` });

  // ---- 4. a generated picture asks which model first ---------------------------------
  await openSettings('tools');
  await p.check('#tool-images');
  const models = await p.locator('select[aria-label="Image model"] option').count();
  check('Settings offers the approved image models', models >= 1);
  await closeSettings();
  await ask('draw me a picture of a leaf');
  const asked = await p.locator('.ask:has-text("pick which image model")').count();
  check('nothing is drawn until the user picks a model', asked >= 1 || (await p.locator('.art.image-art').count()) === 0);

  if (models > 1) {
    await openSettings('tools');
    await p.selectOption('select[aria-label="Image model"]', { index: 1 });
    await closeSettings();
    await ask('draw me a picture of a leaf');
    await p.waitForSelector('.art.image-art img', { timeout: 25000 });
    check('once a model is chosen the picture is drawn and shown',
      await p.locator('.art.image-art img').last().evaluate((el) => el.naturalWidth > 0 || el.complete));
    await p.screenshot({ path: `${SHOTS}/53-image.png` });
  }

  // ---- 5. response length is a visible control that reaches the server ----------------
  await openSettings('limits');
  const seg = p.locator('[aria-label="Response length"] button');
  check('response length is a plain Auto / Short / Normal / Long switch', (await seg.count()) === 4
    && (await seg.first().getAttribute('aria-pressed')) === 'true');
  await seg.nth(3).click();
  check('picking Long marks it as chosen', (await seg.nth(3).getAttribute('aria-pressed')) === 'true');
  check('the tab summary shows the choice', /long/i.test(await p.locator('#tab-limits-btn').innerText()));
  const sent = p.waitForRequest((r) => r.url().includes('/api/chat') && r.method() === 'POST');
  await closeSettings();
  await ask('explain photosynthesis');
  check('the length choice is sent with the message', JSON.parse((await sent).postData()).length === 'long');
  await p.screenshot({ path: `${SHOTS}/54-length.png` });

  // ---- 6. deleting a file removes it from the workspace -------------------------------
  if (!(await p.locator('#files-panel').isVisible())) await p.click('#files-toggle');
  await p.waitForSelector('#file-list .file');
  const n0 = await p.locator('#file-list .file').count();
  await p.locator('#file-list .file .danger-ghost').first().click();
  await p.waitForFunction((n) => document.querySelectorAll('#file-list .file').length < n, n0, { timeout: 8000 });
  check('the bin button deletes a file for good', (await p.locator('#file-list .file').count()) === n0 - 1, `${n0} -> ${await p.locator('#file-list .file').count()}`);
  check('the reader clears when the file it showed is gone', await p.locator('#preview').isHidden());
  await p.screenshot({ path: `${SHOTS}/55-after-delete.png` });

  check('no browser errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  await b.close();
  const bad = ok.filter((x) => !x).length;
  console.log(bad ? `\n${bad} FAILED` : `\nall ${ok.length} document checks passed`);
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error('crashed:', e.message.split('\n').slice(0, 6).join('\n')); process.exit(2); });
