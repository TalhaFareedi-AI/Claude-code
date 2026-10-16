// Real browser regression checks for team controls, plan approval and interrupted streams.
// Start backend/tests/demo_server.py first, then: CHROME=/usr/bin/chromium node scripts/team_ui_check.cjs [url]
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const BASE = process.argv[2] || 'http://127.0.0.1:8765';
const results = [];
const check = (name, ok) => { assert.ok(ok, name); results.push(name); console.log('PASS  ' + name); };

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 820 } });
    const page = await context.newPage(), errors = [], requests = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('request', (r) => { if (r.url().endsWith('/api/chat') && r.method() === 'POST') requests.push(r.postDataJSON()); });
    await page.goto(BASE); await page.waitForSelector('.welcome');
    await page.selectOption('#dev-plan', 'pro'); await page.waitForFunction(() => document.querySelector('#plan-badge').textContent === 'pro');
    await page.click('.chip:has-text("Team:")');
    await page.locator('[aria-label="Team preset"] button:has-text("Full team")').click();
    const planners3 = await page.getByLabel('Number of planners', { exact: true }).inputValue();
    const architects4 = await page.locator('.team-architects input:checked').count(), depth = await page.getByLabel('Planning depth', { exact: true }).inputValue();
    await page.click('#tab-research-btn'); const researchers3 = await page.getByLabel('Number of researchers', { exact: true }).inputValue(); await page.click('#tab-planning-btn');
    check('Full team selects three planners, three researchers and four architects', planners3 === '3' && researchers3 === '3' && architects4 === 4 && depth === 'deep');
    await page.locator('.team-agent summary').filter({ hasText: /^Planner$/ }).click();
    const planner3 = page.getByLabel('Planner 3 model', { exact: true });
    const chosen = await planner3.locator('option:not([disabled])').nth(1).getAttribute('value');
    await planner3.selectOption(chosen);
    await page.getByLabel('Planner 1 model', { exact: true }).selectOption(chosen);
    await page.locator('.team-instance summary').filter({ hasText: 'Planner 3 limits' }).click();
    await page.getByLabel('Planner 3 effort', { exact: true }).selectOption('high');
    await page.getByLabel('Planner 3 credit cap', { exact: true }).fill('8'); await page.getByLabel('Planner 3 credit cap', { exact: true }).blur();
    await page.click('#tab-research-btn');
    await page.locator('.team-agent summary').filter({ hasText: /^Researcher$/ }).click();
    await page.locator('.team-instance summary').filter({ hasText: 'Researcher 3 limits' }).click();
    await page.getByLabel('Researcher 3 search engine', { exact: true }).selectOption('exa');
    await page.getByLabel('Researcher 3 search limit', { exact: true }).fill('3'); await page.getByLabel('Researcher 3 search limit', { exact: true }).blur();
    await page.click('#tab-build-btn'); await page.getByLabel('Explain answers like a tutor (treat me as a learner)', { exact: true }).check();   // teaching is opt-in
    await page.click('#tab-planning-btn'); await page.getByLabel('Team profile name', { exact: true }).fill('Research profile');
    await page.getByRole('button', { name: 'Save profile', exact: true }).click();
    check('Named profiles preserve positional model choices and teacher preference', await page.evaluate(() => {
      const settings = JSON.parse(localStorage.getItem('sh.settings'));
      return settings.team.planners.models[0] && settings.team.planners.models[2] && settings.team.planners.agents[2].effort === 'high' && settings.team.planners.agents[2].max_credits === 8 && settings.team.researchers.agents[2].engine === 'exa' && settings.team.researchers.agents[2].max_searches_each === 3 && settings.teacher_enabled === true && settings.team.name === 'Research profile';
    }));
    await page.locator('[aria-label="Team preset"] button:has-text("Fast")').click();
    await page.getByLabel('Saved team profile', { exact: true }).selectOption('Research profile');
    const reloaded3 = await page.getByLabel('Number of planners', { exact: true }).inputValue(); await page.click('#tab-build-btn');
    check('Loading a profile restores all its controls', reloaded3 === '3' && await page.getByLabel('Explain answers like a tutor (treat me as a learner)', { exact: true }).isChecked());
    await page.click('#tab-planning-btn');
    await page.locator('[aria-label="Team preset"] button:has-text("Balanced")').click();
    await page.getByLabel('Number of planners', { exact: true }).fill('2'); await page.getByLabel('Number of planners', { exact: true }).blur();
    await page.getByLabel('Plan mode', { exact: true }).selectOption('ask');
    await page.click('#tab-research-btn'); await page.getByLabel('Number of researchers', { exact: true }).fill('0'); await page.getByLabel('Number of researchers', { exact: true }).blur();
    await page.click('#tab-build-btn'); await page.getByLabel('Team credit cap', { exact: true }).fill('80'); await page.getByLabel('Team credit cap', { exact: true }).blur();
    await page.click('#settings-close');
    await page.fill('#composer-text', 'Give a detailed compound interest explanation, calculate it and draw a chart.'); await page.click('#send-btn');
    const approve = page.getByRole('button', { name: 'Approve plan and continue', exact: true });
    const confirm = page.getByRole('button', { name: /^Continue \(up to/ });
    await Promise.race([approve.waitFor({ state: 'visible', timeout: 20000 }), confirm.waitFor({ state: 'visible', timeout: 20000 })]);
    if (await confirm.isVisible()) await confirm.click();
    await approve.waitFor({ state: 'visible', timeout: 20000 });
    check('Ask mode waits for an editable plan before building', await page.locator('.plan-editor textarea').count() > 0 && await page.locator('.agent-card[data-agent="builder"], .agent-card[data-agent^="architect"], .agent-card[data-agent^="researcher"], .art.chart').count() === 0);
    const originalTask = await page.evaluate(() => JSON.parse(localStorage.getItem('sh.run')).task);
    await page.reload(); await approve.waitFor({ state: 'visible', timeout: 20000 });
    await page.waitForFunction(() => !document.querySelector('.run.working'));
    check('Pending plan approval and its request context survive reload', await page.evaluate((task) => {
      const run = JSON.parse(localStorage.getItem('sh.run')); return run.task === task && !!run.payload.request_id;
    }, originalTask));
    await page.getByLabel('Step 1 goal', { exact: true }).fill(''); await approve.click();
    check('Plan editing rejects an empty goal without starting a run', await page.locator('.plan-editor + [role="alert"]').isVisible());
    await page.getByLabel('Step 1 goal', { exact: true }).fill('Calculate compound interest and verify the arithmetic.');
    await approve.click();
    await page.waitForFunction(() => !document.querySelector('.run.working') && document.querySelector('.answer'), null, { timeout: 25000 });
    const approval = requests.find((r) => r.approved_plan);
    check('Approval resumes the original task with edited goals and a new request identity', approval?.continue_task === originalTask && approval.approved_plan[0].goal.startsWith('Calculate compound') && approval.confirm && approval.request_id !== requests[0].request_id && approval.teacher_enabled === true && approval.max_credits > 0);
    const chatA = await page.evaluate(() => JSON.parse(localStorage.getItem('sh.conv')));
    await page.reload(); await page.waitForSelector('.answer'); await page.click('.chip:has-text("Team:")');
    const mode_ = await page.getByLabel('Plan mode', { exact: true }).inputValue(); await page.click('#tab-build-btn');
    check('Conversation reload restores team and optional teacher settings', mode_ === 'ask' && await page.getByLabel('Explain answers like a tutor (treat me as a learner)', { exact: true }).isChecked());
    await page.click('#settings-close'); await page.click('#new-chat'); await page.click('.chip:has-text("Team:")');
    await page.locator('[aria-label="Team preset"] button:has-text("Fast")').click();
    await page.click('#tab-build-btn'); await page.getByLabel('Explain answers like a tutor (treat me as a learner)', { exact: true }).uncheck();   // this chat wants direct answers
    await page.click('#settings-close');
    let truncated = false;
    await page.route('**/api/chat', async (route) => {
      if (truncated) return route.continue();
      truncated = true;
      const upstream = await route.fetch();
      const complete = await upstream.text();
      await route.fulfill({ response: upstream, body: complete.split('\n\n').slice(0, 2).join('\n\n') + '\n\n' });
    });
    const countBefore = requests.length;
    await page.fill('#composer-text', 'Hello from a second chat'); await page.click('#send-btn');
    await page.waitForFunction(() => !document.querySelector('.run.working') && document.querySelector('.answer'), null, { timeout: 20000 });
    check('Interrupted streams reconnect to saved events without submitting another run', requests.length === countBefore + 1 && await page.locator('.run-body').textContent().then((s) => s.includes('Reconnecting')) && await page.evaluate(() => JSON.parse(localStorage.getItem('sh.run')) === null));
    check('A new message receives a fresh request identity', requests.at(-1).request_id && requests.at(-1).request_id !== approval.request_id);
    await page.unroute('**/api/chat');
    await page.click('#new-chat');
    let lostResponse = false;
    await page.route('**/api/chat', async (route) => {
      if (lostResponse) return route.continue();
      lostResponse = true;
      await route.fetch(); // The server accepted and completed the task, but the client never saw hello.
      await route.abort('failed');
    });
    await page.fill('#composer-text', 'Hello after a lost response'); await page.click('#send-btn');
    await page.getByRole('button', { name: 'Retry', exact: true }).waitFor({ state: 'visible', timeout: 15000 });
    const firstTry = requests.at(-1);
    await page.getByRole('button', { name: 'Retry', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.run.working') && document.querySelector('.answer'), null, { timeout: 15000 });
    const lastConversation = await page.evaluate(async () => {
      const id = JSON.parse(localStorage.getItem('sh.conv')); return (await fetch(`/api/conversations/${id}`)).json();
    });
    check('Retrying a lost initial response reuses its request identity and creates no duplicate messages', requests.at(-1).request_id === firstTry.request_id && lastConversation.messages.filter((m) => m.role === 'user').length === 1 && lastConversation.messages.filter((m) => m.role === 'assistant').length === 1);
    await page.unroute('**/api/chat');
    // Restore the first chat's saved choices, independent from the current team's profile.
    await page.evaluate((id) => { localStorage.setItem('sh.conv', JSON.stringify(id)); }, chatA);
    await page.reload(); await page.waitForSelector('.answer'); await page.click('.chip:has-text("Team:")');
    const mode2_ = await page.getByLabel('Plan mode', { exact: true }).inputValue(); await page.click('#tab-build-btn');
    check('Each chat keeps its own team selection', mode2_ === 'ask' && await page.getByLabel('Explain answers like a tutor (treat me as a learner)', { exact: true }).isChecked());
    await page.click('#settings-close');
    const mobile = await browser.newContext({ viewport: { width: 390, height: 780 }, isMobile: true, hasTouch: true });
    const phone = await mobile.newPage(); phone.on('pageerror', (e) => errors.push(e.message));
    await phone.goto(BASE); await phone.waitForSelector('.welcome'); await phone.click('.chip:has-text("Team:")');
    await phone.locator('[aria-label="Team preset"] button:has-text("Full team")').click();
    check('Team controls fit a phone without horizontal scrolling', await phone.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.querySelector('#settings-body').scrollWidth <= document.querySelector('#settings-body').clientWidth));
    check('Parallel researcher cards stay separate and citation links reject unsafe URLs', await page.evaluate(async () => {
      const { RunView, ArtifactStore } = await import('/js/runview.js');
      const view = new RunView({ artifacts: new ArtifactStore() });
      view.handle({ type: 'tool_start', tool: 'web_search', agent: 'researcher1', title: 'first pending' });
      view.handle({ type: 'tool_start', tool: 'web_search', agent: 'researcher2', title: 'second pending' });
      view.handle({ type: 'tool_result', tool: 'web_search', agent: 'researcher2', ok: true, summary: 'second complete' });
      const cards = [...view.el.querySelectorAll('.card .what')].map((el) => el.textContent);
      view.handle({ type: 'sources', agent: 'researcher2', sources: [{ url: 'javascript:alert(1)', title: 'bad' }, { url: 'https://example.org/paper', title: 'Paper' }, { url: 'https://example.org/paper', title: 'Duplicate' }] });
      return cards[0] === 'first pending' && cards[1].includes('second complete') && view.el.querySelectorAll('.source-chips a').length === 1 && view.el.querySelector('.source-chips a').rel.includes('noopener');
    }));
    check('No browser errors', errors.length === 0);
    console.log(`\nall ${results.length} team UI checks passed`);
  } finally { await browser.close(); }
})().catch((e) => { console.error(e); process.exitCode = 1; });
