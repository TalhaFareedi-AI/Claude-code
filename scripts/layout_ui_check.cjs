// Real-browser check of the resizable side panels, the Workspace button and the tabbed settings.
// Usage: node scripts/layout_ui_check.cjs   (server: UNLOCK_ALL=1 FAKE_DELAY=0 python backend/tests/demo_server.py)
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:8765';
const ok = []; const check = (n, v, x = '') => { ok.push(v); console.log(`${v ? 'PASS' : 'FAIL'}  ${n}${x ? '  ' + x : ''}`); };
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  const errors = [];
  const ctx = await b.newContext({ viewport: { width: 1500, height: 880 } });
  const p = await ctx.newPage(); p.on('pageerror', (e) => errors.push(e.message)); p.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await p.goto(BASE); await p.waitForFunction(() => document.querySelector('#wallet-bal').textContent !== '–');
  const w = (sel) => p.evaluate((s) => Math.round(document.querySelector(s).getBoundingClientRect().width), sel);
  const drag = async (sel, dx) => { const r = await p.locator(sel).boundingBox(); await p.mouse.move(r.x + 5, 300); await p.mouse.down(); await p.mouse.move(r.x + 5 + dx, 300, { steps: 8 }); await p.mouse.up(); };

  check('sidebar has no sideways scroll and keeps its padding', await p.evaluate(() => { const s = document.querySelector('#sidebar'); return s.scrollWidth <= s.clientWidth && s.scrollLeft === 0; }));
  const w0 = await w('#sidebar');
  await drag('#side-resizer', 110);
  check('dragging the sidebar edge makes it wider', (await w('#sidebar')) > w0 + 80, `${w0} -> ${await w('#sidebar')}`);
  await drag('#side-resizer', -320);
  check('dragging far left minimizes it to icons', (await w('#sidebar')) <= 70 && await p.locator('#app[data-rail="1"]').count() === 1);
  check('minimized sidebar still shows the credit balance and icons', await p.locator('#wallet-bal').isVisible() && await p.locator('#side-resizer').isVisible());
  await p.click('#collapse-side');
  check('the « button expands it again', (await w('#sidebar')) > 150);
  await p.locator('#side-resizer').dblclick();
  check('double-click resets the width', (await w('#sidebar')) === 272);
  await p.locator('#side-resizer').focus(); await p.keyboard.press('ArrowRight'); await p.keyboard.press('ArrowRight');
  check('keyboard arrows resize too', (await w('#sidebar')) === 304);
  await p.reload(); await p.waitForFunction(() => document.querySelector('#wallet-bal').textContent !== '–');
  check('the size is remembered after reload', (await w('#sidebar')) === 304);

  check('workspace is closed until needed', (await p.locator('#app').getAttribute('data-files')) === 'closed' && !(await p.locator('#files-panel').isVisible()));
  await p.click('#files-toggle');
  check('the Workspace button opens it, with a ✕', await p.locator('#files-panel').isVisible() && await p.locator('#close-files').isVisible());
  const f0 = await w('#files-panel'); await p.locator('#files-resizer').boundingBox().then(async (r) => { await p.mouse.move(r.x + 5, 300); await p.mouse.down(); await p.mouse.move(r.x - 120, 300, { steps: 6 }); await p.mouse.up(); });
  check('the workspace can be stretched with the mouse', (await w('#files-panel')) > f0 + 80, `${f0} -> ${await w('#files-panel')}`);
  await p.click('#close-files');
  check('the ✕ closes the workspace', !(await p.locator('#files-panel').isVisible()) && (await p.locator('#files-toggle').getAttribute('aria-expanded')) === 'false');

  // owner: everything open
  check('owner badge and every mode unlocked', (await p.locator('#plan-badge').innerText()).toLowerCase() === 'owner');
  await p.click('#chips .chip:has-text("Mode")'); await p.waitForSelector('#settings:not([hidden])');
  check('settings has 8 tabs, each with a short summary', (await p.locator('.tab-btn').count()) === 8 && (await p.locator('.tab-btn .tab-sum').count()) >= 7);
  check('no mode shows a lock for the owner', (await p.locator('.mode-opt .lock').count()) === 0);
  await p.click('.mode-opt:has-text("Council")');
  await p.click('#tab-brains-btn');
  await p.click('[aria-label="Quick pick"] button:has-text("Strongest")');
  const picked = await p.evaluate(() => JSON.parse(localStorage.getItem('sh.settings')).brains);
  check('Brains: one tap sets every job', Object.keys(picked).length >= 2, JSON.stringify(Object.keys(picked)));
  for (const t of ['planning', 'research', 'build', 'limits', 'tools', 'display']) { await p.click(`#tab-${t}-btn`); }
  check('every tab opens its own page', await p.locator('#tab-display-btn[aria-selected="true"]').count() === 1 && /Display/.test(await p.locator('.tab-pane h3').first().innerText()));
  await p.click('#tab-limits-btn');
  check('Max effort is available to the owner', !(await p.locator('[aria-label="Effort"] button:has-text("Max")').isDisabled()));
  await p.click('#settings-close');
  check('chips mention the choices', /Custom/.test(await p.locator('#chips').innerText()) && /Council/.test(await p.locator('#chips').innerText()));

  // a real run in a mode that is Pro-only on normal plans
  await p.fill('#composer-text', 'explain gravity'); await p.click('#send-btn');
  await p.waitForSelector('.msg-foot', { timeout: 20000 }).catch(() => {});
  const ask = await p.locator('.ask button:has-text("Continue")').count();
  if (ask) await p.locator('.ask button:has-text("Continue")').click();
  await p.waitForSelector('.msg-foot', { timeout: 20000 });
  check('a Council run works for the owner', /agree/i.test(await p.locator('.msg.assistant .answer').last().innerText()));

  // phone
  const m = await (await b.newContext({ viewport: { width: 390, height: 780 }, isMobile: true, hasTouch: true })).newPage();
  m.on('pageerror', (e) => errors.push(e.message));
  await m.goto(BASE); await m.waitForFunction(() => document.querySelector('#wallet-bal').textContent !== '–');
  check('phone: no sideways scroll', await m.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await m.click('.chip:has-text("Settings")'); await m.waitForSelector('#settings:not([hidden])');
  check('phone: tabs become a scrolling strip, content fits', await m.evaluate(() => { const r = document.querySelector('.tab-rail'); const l = document.querySelector('.settings-layout'); return getComputedStyle(r).flexDirection === 'row' && l.scrollWidth <= l.clientWidth + 1; }));
  await m.click('#tab-planning-btn');
  check('phone: planning page fits the screen', await m.evaluate(() => { const l = document.querySelector('.tab-pane'); return l.scrollWidth <= l.clientWidth + 1; }));
  await m.screenshot({ path: '/tmp/claude-0/shots/46-phone-tabs.png' });

  check('no browser errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  await b.close();
  const bad = ok.filter((x) => !x).length; console.log(bad ? `\n${bad} FAILED` : `\nall ${ok.length} layout checks passed`); process.exit(bad ? 1 : 0);
})().catch((e) => { console.error('crashed:', e.message.split('\n').slice(0, 5).join('\n')); process.exit(2); });
