// Isolated browser checks for chart precision, responsiveness and independent geometry.
// No API key, app server or paid calls are needed: node scripts/chart_regression.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require('playwright');

const frontend = path.resolve(__dirname, '../frontend');
const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  if (pathname === '/') {
    res.setHeader('Content-Type', 'text/html');
    return res.end('<!doctype html><style>.chart-svg{display:block;width:100%;height:auto}.chart-box{position:relative}.tip{position:absolute}</style><body></body>');
  }
  const file = path.resolve(frontend, '.' + pathname);
  if (!file.startsWith(frontend + path.sep) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/plain');
  fs.createReadStream(file).pipe(res);
});

let browser;
async function bounded(promise) {
  let timeout;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timeout = setTimeout(() => reject(new Error('Chart rendering blocked the browser for over 5 seconds.')), 5000);
    })]);
  } finally { clearTimeout(timeout); }
}

(async () => {
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const executablePath = [process.env.CHROME, chromium.executablePath(), '/usr/bin/chromium', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find((p) => p && fs.existsSync(p));
  browser = await chromium.launch({ ...(executablePath ? { executablePath } : {}), args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const results = await bounded(page.evaluate(async () => {
    const { renderChart } = await import('/js/charts.js');
    const cases = [
      ['ordinary', 'x*x', 0, 10],
      ['one-ULP range at a large baseline', '1e20+x*16384', 0, 1],
      ['positive constant', '1e308', 0, 1],
      ['negative constant', '-1e308', 0, 1],
      ['opposite large endpoints', '1e308*(2*x-1)', 0, 1],
      ['subnormal values', '1e-323*x', 0, 1],
      ['large x range', 'x/1e308', 0, 1e308],
    ];
    return cases.map(([title, formula, from, to]) => {
      const chart = renderChart({ chart: 'line', title, inputs: [], x: { label: 'x', from: String(from), to: String(to) }, steps: 60, lines: [{ name: 'y', formula }] });
      const svg = chart.querySelector('svg');
      const invalid = [...svg.querySelectorAll('*')].some((el) => [...el.attributes].some((a) => /NaN|Infinity/.test(a.value)));
      return { title, valid: !!svg.querySelector('path[d]') && !invalid };
    });
  }));
  for (const result of results) {
    assert(result.valid, `${result.title} produced non-finite SVG coordinates.`);
    console.log(`PASS  ${result.title} renders without blocking or invalid coordinates`);
  }

  await bounded(page.evaluate(async () => {
    const { renderChart } = await import('/js/charts.js');
    for (const [id, width] of [['narrow', 320], ['wide', 640]]) {
      const host = document.createElement('div');
      host.id = id; host.style.width = `${width}px`;
      document.body.append(host);
      host.append(renderChart({ chart: 'line', title: id, inputs: [], x: { label: 'x', from: '0', to: '10' }, steps: 60, lines: [{ name: 'y', formula: 'x' }] }));
    }
  }));
  await page.waitForFunction(() => document.querySelector('#narrow svg').viewBox.baseVal.width === 320 && document.querySelector('#wide svg').viewBox.baseVal.width === 640);
  const svg = page.locator('#narrow svg');
  const bounds = await svg.boundingBox();
  // Point at x = 7 on the narrow chart after the wide chart has redrawn.
  const chartX = 56 + (320 - 56 - 14) * 0.7;
  await page.mouse.move(bounds.x + (chartX / 320) * bounds.width, bounds.y + bounds.height / 2);
  const hover = await page.locator('#narrow .tip').innerText();
  assert.equal(hover.split('\n')[0], 'x: 7');
  const markerX = await svg.locator('g circle').first().getAttribute('cx');
  assert(Math.abs(Number(markerX) - chartX) < 0.01, 'Narrow chart hover used another chart\'s geometry.');
  console.log('PASS  differently sized charts retain independent hover geometry');
  assert.deepEqual(errors, [], 'Unexpected browser errors.');
  console.log(`All ${results.length + 1} chart regressions passed.`);
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
});
