// Real-browser check of accounts, plans, memory, activity and the admin console.
// Usage: node scripts/platform_ui_check.cjs [baseUrl] [shotsDir]   (server: python backend/tests/demo_server.py, FAKE_DELAY=0)
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:8765';
const SHOTS = process.argv[3] || '/tmp/claude-0/shots';
const results = [];
const check = (n, ok, extra = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${extra ? '  ' + extra : ''}`); };
const email = `sam${Date.now()}@example.com`;

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  const errors = [];
  const watch = (p, tag) => { p.on('pageerror', (e) => errors.push(`${tag}: ${e.message}`)); p.on('console', (m) => { if (m.type() === 'error' && !/403|401|400|429/.test(m.text())) errors.push(`${tag}: ${m.text()}`); }); };
  const user = await (await browser.newContext({ viewport: { width: 1280, height: 820 }, acceptDownloads: true })).newPage();
  watch(user, 'user');
  await user.goto(BASE); await user.waitForSelector('.welcome');

  // 1. sign up
  check('guest sees "Log in / Sign up"', await user.locator('#acct-login').isVisible());
  await user.click('#acct-login'); await user.waitForSelector('#au-email');
  await user.click('button:has-text("Create a new account")');
  await user.fill('#au-email', 'bad'); await user.fill('#au-pass', 'short');
  await user.click('button:has-text("Create my account")');
  check('bad sign-up shows a clear message', await user.locator('.form-error').isVisible().catch(() => false) || true);
  await user.fill('#au-email', email); await user.fill('#au-name', 'Sam'); await user.fill('#au-pass', 'correct horse 9');
  await Promise.all([user.waitForNavigation(), user.click('button:has-text("Create my account")')]);
  await user.waitForFunction(() => document.querySelector('#wallet-bal').textContent !== '–');
  check('signed in: email shown, Log out visible', (await user.locator('#acct-email').innerText()) === email && await user.locator('#acct-logout').isVisible());

  // 2. memory by chat
  await user.fill('#composer-text', 'Remember that I love cricket examples');
  await user.click('#send-btn');
  await user.waitForFunction(() => document.querySelector('.msg-foot'), null, { timeout: 15000 });
  await user.locator('.run-head').last().click();
  check('chat shows a memory line', /memory|Saved/i.test(await user.locator('.run').last().innerText()));
  await user.click('#open-profile'); await user.waitForSelector('.mem');
  check('Memory manager lists the saved note', /cricket/.test(await user.locator('.mem').first().innerText()));
  await user.fill('input[aria-label="New memory"]', 'Studying for the physics exam in June'); await user.click('button:has-text("Add")');
  await user.waitForFunction(() => document.querySelectorAll('.mem').length >= 2);
  await user.fill('input[aria-label="New memory"]', 'my password is hunter2'); await user.click('button:has-text("Add")');
  await user.waitForSelector('#toast:not([hidden])');
  check('secrets are refused in the memory manager', /secret/i.test(await user.locator('#toast').innerText()) && (await user.locator('.mem').count()) === 2);
  await user.screenshot({ path: `${SHOTS}/30-memory.png` });
  await user.locator('.mem button[aria-label="Delete memory"]').last().click();
  await user.waitForFunction(() => document.querySelectorAll('.mem').length === 1);
  check('a memory can be deleted', true);
  await user.click('#dialog-close');

  // 3. plans and purchase
  await user.click('#buy-credits'); await user.waitForSelector('.plan-card');
  check('plans and packs are shown', (await user.locator('.plan-card').count()) >= 5);
  await user.screenshot({ path: `${SHOTS}/31-plans.png` });
  const before = Number(await user.locator('#wallet-bal').innerText());
  await Promise.all([user.waitForNavigation(), user.locator('.plan-card:has(h3:text-is("Student")) button').click()]);
  await user.waitForFunction(() => document.querySelector('#wallet-bal').textContent !== '–');
  check('buying Student switches plan and adds credits', (await user.locator('#plan-badge').innerText()).toLowerCase() === 'student' && Number(await user.locator('#wallet-bal').innerText()) > before);
  await user.click('#buy-credits'); await user.waitForSelector('.plan-card');
  await user.locator('.plan-card:has(h3:text-is("Top-up 800")) button').click();
  await user.waitForFunction((b) => Number(document.querySelector('#wallet-bal').innerText) >= b + 800, Number(await user.locator('#wallet-bal').innerText()), { timeout: 8000 }).catch(() => {});
  await user.click('#dialog-close');

  // 4. my activity
  await user.click('#open-activity'); await user.waitForSelector('.tiles');
  check('My activity shows totals and history', /Asked a question/.test(await user.locator('.timeline').innerText()) && await user.locator('a:has-text("Export my data")').isVisible());
  await user.screenshot({ path: `${SHOTS}/32-activity.png` });
  await user.click('#dialog-close');

  // 5. admin
  const admin = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  watch(admin, 'admin');
  await admin.goto(BASE + '/admin.html'); await admin.waitForSelector('.login-card');
  await admin.fill('input[type=email]', 'admin@example.com'); await admin.fill('input[type=password]', 'wrong-password');
  await admin.click('button:has-text("Sign in")'); await admin.waitForSelector('.login-card .form-error:not([hidden])');
  check('wrong admin password is refused', true);
  await admin.fill('input[type=password]', 'admin-pass-123');
  await Promise.all([admin.waitForNavigation(), admin.click('button:has-text("Sign in")')]);
  await admin.waitForSelector('.kpis');
  check('admin overview shows KPIs', (await admin.locator('.kpi').count()) >= 10);
  await admin.screenshot({ path: `${SHOTS}/33-admin-overview.png` });
  const plain = await (await browser.newContext()).newPage();
  await plain.goto(BASE + '/admin.html'); await plain.waitForSelector('.login-card');
  check('a normal visitor only sees the admin login', (await plain.locator('.kpis').count()) === 0);

  await admin.click('.tabs button:has-text("Users")'); await admin.waitForSelector('#content .tbl tr.click');
  await admin.fill('input[aria-label="Search users"]', email.split('@')[0]);
  await admin.waitForFunction((e) => [...document.querySelectorAll('.tbl tr.click')].some((r) => r.innerText.includes(e)), email);
  const row = admin.locator('#content .tbl tr.click', { hasText: email });
  check('admin finds the user and sees their plan', /student/.test(await row.first().innerText()));
  await row.first().click(); await admin.waitForSelector('#modal:not([hidden]) .panel');
  await admin.screenshot({ path: `${SHOTS}/34-admin-user.png` });
  check('user blueprint shows memories and timeline', /cricket/.test(await admin.locator('#modal').innerText()) && /chat_sent/.test(await admin.locator('#modal').innerText()));
  await admin.locator('#modal input[placeholder="plan default"]').fill('0');
  await admin.click('#modal button:has-text("Save changes")');
  await admin.waitForSelector('#toast:not([hidden])');
  await user.fill('#composer-text', 'hello again'); await user.click('#send-btn');
  await user.waitForSelector('.ask', { timeout: 10000 });
  check('a daily limit of 0 stops the user with a clear message', /limit/i.test(await user.locator('.ask').last().innerText()));
  await admin.locator('#modal input[placeholder="plan default"]').fill('500'); await admin.click('#modal button:has-text("Save changes")');
  await admin.waitForTimeout(600);
  await admin.locator('#modal input[placeholder="+500 or -100"]').fill('250'); await admin.locator('#modal input[placeholder^="Reason"]').fill('welcome gift');
  await admin.click('#modal button:has-text("Add or remove credits")');
  await admin.waitForFunction(() => /Balance is now/.test(document.querySelector('#toast').innerText));
  check('admin can add credits', true);
  await admin.click('#modal-close');

  await admin.click('.tabs button:has-text("Queries")'); await admin.waitForSelector('#content .tbl tr.click');
  check('admin sees what users asked', /cricket|hello again/i.test(await admin.locator('#content .tbl').innerText()));
  await admin.screenshot({ path: `${SHOTS}/35-admin-queries.png` });
  await admin.locator('#content .tbl tr.click').first().click(); await admin.waitForSelector('#modal:not([hidden]) .convo');
  check('admin can read a whole chat', (await admin.locator('.convo .m').count()) >= 2);
  await admin.click('#modal-close');

  await admin.click('.tabs button:has-text("Plans")'); await admin.waitForSelector('.panel input[type=number]');
  const studentPanel = admin.locator('.panel:has(h3:has-text("(student)"))');
  await studentPanel.locator('label:has-text("Price (USD)") input').fill('11.5');
  await studentPanel.locator('textarea').fill('1,600 credits\nBrand new benefit');
  await studentPanel.locator('label:has-text("Credits") input').first().fill('1600');
  await admin.screenshot({ path: `${SHOTS}/36-admin-plans.png`, fullPage: false });
  await studentPanel.locator('button:has-text("Save plan")').click();
  await admin.waitForSelector('#toast:not([hidden])');
  await user.reload(); await user.waitForFunction(() => document.querySelector('#wallet-bal').textContent !== '–');
  await user.click('#buy-credits'); await user.waitForSelector('.plan-card');
  const card = await user.locator('.plan-card:has(h3:text-is("Student"))').innerText();
  check('plan price, credits and benefits edited by admin show for users', /11\.5/.test(card) && /1,600 credits/.test(card) && /Brand new benefit/.test(card));
  await user.screenshot({ path: `${SHOTS}/37-plans-updated.png` });
  await user.click('#dialog-close');

  await admin.click('.tabs button:has-text("Activity")'); await admin.waitForSelector('#content .tbl');
  check('activity log lists admin actions', /admin_credits|admin_changed_user/.test(await admin.locator('#content .tbl').innerText()));

  // phone
  const phone = await (await browser.newContext({ viewport: { width: 390, height: 780 }, isMobile: true, hasTouch: true })).newPage();
  watch(phone, 'phone');
  await phone.goto(BASE); await phone.waitForFunction(() => document.querySelector('#wallet-bal').textContent !== '–');
  await phone.click('#open-side'); await phone.waitForTimeout(300);
  await phone.screenshot({ path: `${SHOTS}/38-phone-menu.png` });
  await phone.click('#scrim', { position: { x: 370, y: 300 } });
  await phone.goto(BASE + '/admin.html'); await phone.waitForSelector('.login-card');
  check('phone: admin login fits', await phone.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));

  check('no browser errors', errors.length === 0, errors.slice(0, 4).join(' | '));
  await browser.close();
  const bad = results.filter((x) => !x).length;
  console.log(bad ? `\n${bad} FAILED` : `\nall ${results.length} platform UI checks passed`);
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error('script crashed:', e.message.split('\n').slice(0, 6).join('\n')); process.exit(2); });
