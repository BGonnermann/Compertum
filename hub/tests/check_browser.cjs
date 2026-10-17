/* Browser checks use the existing bundled Playwright library. No package install. */
const { chromium } = require(process.argv[2] || 'playwright');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const output = process.argv[3];
const base = process.argv[4] || 'http://127.0.0.1:8767';
if (!output || !path.isAbsolute(output)) throw new Error('Choose an absolute external evidence folder.');
fs.mkdirSync(output, { recursive: true });
const project = path.resolve(__dirname, '../..');
let passed = 0;
const checks = [];
function check(condition, name) {
  if (!condition) throw new Error(name);
  passed++; checks.push(name);
}
async function main() {
  const browser = await chromium.launch({ headless: true, ...(process.argv[5] ? { executablePath: process.argv[5] } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, deviceScaleFactor: 1 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.getByText('Connected to saved project records', { exact: true }).waitFor();
    check(await page.title() === 'Compertum Hub', 'The real Hub page loads.');
    const actual = await (await page.request.get(`${base}/api/snapshot`)).json();
    check(actual.catalogue.entries.length > 8, 'The catalogue includes actual tracked project records.');
    check(actual.work.available, 'Read-only Git observations are available.');
    const original = fs.readFileSync(path.join(project, 'docs/CURRENT_CHECKPOINT.md'));
    check(actual.checkpoint.sha256 === crypto.createHash('sha256').update(original).digest('hex'), 'The checkpoint fingerprint matches the original file.');
    check((await page.locator('#overview-page h2').first().textContent()) === actual.checkpoint.summary, 'The visible summary matches the actual checkpoint.');
    check(await page.locator('#overview-page').getByText('Not observed', { exact: true }).isVisible(), 'Running work is not inferred from saved files.');
    await page.screenshot({ path: path.join(output, 'hub-overview-desktop.png'), fullPage: true });
    await page.getByRole('button', { name: 'Current work', exact: true }).click();
    check(await page.locator('#work-page').isVisible(), 'Current work opens.');
    check((await page.locator('#work-page').innerText()).includes('Observed file changes'), 'Current work explains file-change limits.');
    check((await page.locator('#work-page').innerText()).includes('hub/'), 'Current work shows this actual Hub change.');
    await page.getByRole('button', { name: 'Results', exact: true }).click();
    check(await page.locator('#results-page').isVisible(), 'Results opens.');
    const values = await page.locator('#results-page .big-number').allTextContents();
    check(values[0] === String(actual.results.source.passed), 'The source count matches the current checkpoint.');
    check(values[1] === String(actual.results.installed.passed), 'The installed count stays separate and matches the checkpoint.');
    await page.getByRole('button', { name: 'Project map', exact: true }).click();
    check(await page.locator('.map-node').count() === actual.milestones.length, 'The map shows the actual milestone rows.');
    await page.locator('.map-node').filter({ hasText: 'M0' }).click();
    check((await page.locator('#map-page .surface').first().innerText()).includes('ACCEPTED'), 'Selecting M0 opens its recorded acceptance and requirements.');
    const pdf = await page.request.get(`${base}/project-map.pdf`);
    check(pdf.status() === 200 && (await pdf.body()).subarray(0, 4).toString() === '%PDF', 'The actual project-map PDF is available.');
    await page.screenshot({ path: path.join(output, 'hub-map-desktop.png'), fullPage: true });
    await page.getByRole('button', { name: 'Source records', exact: true }).click();
    await page.locator('#record-search').fill('CURRENT_CHECKPOINT');
    check(await page.locator('.record-choice').count() === 1, 'Source search finds the actual current checkpoint.');
    await page.locator('.record-choice').click();
    await page.locator('.fingerprint').waitFor();
    check((await page.locator('#record-text').textContent()).replaceAll('\r\n', '\n') === original.toString('utf8').replace(/^\uFEFF/, '').replaceAll('\r\n', '\n'), 'The source viewer displays the actual file.');
    check((await page.locator('#record-heading').innerText()).includes(actual.checkpoint.sha256), 'The source viewer shows the correct content fingerprint.');
    await page.screenshot({ path: path.join(output, 'hub-records-desktop.png'), fullPage: true });
    await page.route('**/api/record?*', route => route.fulfill({ json: { path: 'docs/CURRENT_CHECKPOINT.md', status: 'available', modified_at: actual.read_at, bytes: 28, sha256: 'fixture', text: '<script>window.hubInjected=1</script>' } }));
    await page.locator('.record-choice').click();
    await page.waitForFunction(() => document.getElementById('record-text').textContent.includes('hubInjected'));
    check(await page.evaluate(() => window.hubInjected === undefined), 'Source markup remains text and cannot run.');
    await page.unroute('**/api/record?*');
    await page.route('**/api/snapshot', route => route.abort());
    await page.getByRole('button', { name: 'Refresh records' }).click();
    await page.getByText('Connection lost · displayed records are stale', { exact: true }).waitFor();
    check(await page.locator('#connection-error').isVisible(), 'A failed refresh marks retained information stale.');
    await page.unroute('**/api/snapshot');
    await page.getByRole('button', { name: 'Refresh records' }).click();
    await page.getByText('Connected to saved project records', { exact: true }).waitFor();
    check(await page.locator('#connection-error').isHidden(), 'A successful retry clears the connection warning.');
    const initialRead = await page.locator('#last-read').textContent();
    await page.waitForFunction(before => document.getElementById('last-read').textContent !== before, initialRead, { timeout: 15000 });
    check(true, 'Visible pages refresh their actual record observations automatically.');
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      for (const name of ['Overview', 'Current work', 'Results', 'Project map', 'Source records']) {
        await page.getByRole('button', { name, exact: true }).click();
        if (name === 'Results') await page.locator('#results-page summary').click();
        check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name} fits at ${width}px, including expanded content.`);
      }
      await page.getByRole('button', { name: 'Overview', exact: true }).click();
      await page.screenshot({ path: path.join(output, `hub-overview-${width}.png`), fullPage: true });
    }
    check(errors.length === 0, `No browser script errors: ${errors.join('; ')}`);
    const report = { passed, failed: 0, errors: 0, skipped: 0, checks, source: 'Real local Hub and current saved project records; failure and markup checks use browser-only responses.' };
    fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } finally { await browser.close(); }
}
main().catch(error => {
  fs.writeFileSync(path.join(output, 'browser-failure.json'), JSON.stringify({ passed, failed: 1, errors: 0, skipped: 0, checks, failure: error.message }, null, 2));
  console.error(error.stack); process.exitCode = 1;
});
