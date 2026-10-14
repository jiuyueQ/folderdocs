// Hierarchy browser regression checks against synthetic demo data only.
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const url = process.env.FOLDERDOCS_TEST_URL || 'http://127.0.0.1:8765';
const account = JSON.parse(fs.readFileSync(process.env.FOLDERDOCS_TEST_ACCOUNT || path.join(root, 'qa-output', 'account.json'), 'utf8'));

(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const folderId = () => new URL(page.url()).searchParams.get('folder');
  const breadcrumb = async () => (await page.locator('.breadcrumb').innerText()).replace(/\s+/g, ' ').trim();
  const navigate = action => Promise.all([page.waitForNavigation(), action()]);
  async function originalBytes(href) {
    const response = await context.request.get(url + href);
    assert.equal(response.status(), 200);
    const bytes = await response.body();
    assert.equal(bytes.subarray(0, 5).toString(), '%PDF-');
    return bytes;
  }
  async function createFolder(name) {
    const existing = page.locator('.folder-tile strong').getByText(name, { exact: true });
    if (await existing.count()) {
      await navigate(() => existing.click());
      return folderId();
    }
    await page.getByRole('button', { name: '在此新建文件夹', exact: true }).click();
    await page.locator('#folder-dialog input[name=name]').fill(name);
    await navigate(() => page.getByRole('button', { name: '创建文件夹', exact: true }).click());
    return folderId();
  }
  try {
    await page.goto(url + '/login/');
    await page.locator('#id_username').fill(account.username);
    await page.locator('#id_password').fill(account.password);
    await navigate(() => page.getByRole('button', { name: '登录我的空间' }).click());
    const homeHref = await page.locator('.folder-nav a[title="家庭账单"]').getAttribute('href');
    const workHref = await page.locator('.folder-nav a[title="合同与凭证"]').getAttribute('href');
    const work = new URL(workHref, url).searchParams.get('folder');
    await page.goto(url + homeHref);
    const home = folderId();
    const year = await createFolder('2026');
    const receipts = await createFolder('电器凭证');
    assert.equal(await breadcrumb(), '我的空间 / 文档库 / 家庭账单 / 2026 / 电器凭证');
    await page.goto(url + '/');
    await page.getByRole('link', { name: '家用电器购买凭证', exact: true }).click();
    const detailUrl = page.url();
    const fileHref = await page.getByRole('link', { name: '下载原文件' }).getAttribute('href');
    const original = await originalBytes(fileHref);
    await page.locator('select[name=folder]').selectOption(receipts);
    assert.equal(await page.locator(`select[name=folder] option[value="${receipts}"]`).innerText(), '家庭账单 / 2026 / 电器凭证');
    await navigate(() => page.getByRole('button', { name: '保存修改', exact: true }).click());
    await page.goto(url + homeHref);
    assert.equal(await page.getByRole('link', { name: '家用电器购买凭证', exact: true }).count(), 0);
    await navigate(() => page.getByRole('checkbox', { name: '包含子文件夹' }).check());
    assert.equal(await page.getByRole('link', { name: '家用电器购买凭证', exact: true }).count(), 1);
    await page.getByRole('searchbox', { name: '搜索文档' }).fill('FD-2026-014');
    await navigate(() => page.getByRole('button', { name: '搜索', exact: true }).click());
    assert.equal(new URL(page.url()).searchParams.get('recursive'), '1');
    assert.equal(await page.locator('.document-card').count(), 1);
    await page.goto(url + '/?folder=' + year);
    assert.equal(await page.getByRole('button', { name: '移除文件夹', exact: true }).isDisabled(), true);
    await page.getByRole('button', { name: '重命名或移动', exact: true }).click();
    assert.equal(await page.locator(`#edit-folder-dialog option[value="${year}"], #edit-folder-dialog option[value="${receipts}"]`).count(), 0);
    await page.locator('#edit-folder-dialog input[name=name]').fill('2026 年');
    await page.locator('#edit-folder-dialog select[name=parent]').selectOption(work);
    await navigate(() => page.getByRole('button', { name: '保存文件夹', exact: true }).click());
    assert.match(await breadcrumb(), /合同与凭证 \/ 2026 年/);
    await page.locator('.folder-tile').getByText('电器凭证', { exact: true }).click();
    assert.equal(folderId(), receipts);
    assert.match(await breadcrumb(), /合同与凭证 \/ 2026 年 \/ 电器凭证/);
    const preserved = await originalBytes(fileHref);
    assert.equal(Buffer.compare(original, preserved), 0);
    await page.goto(detailUrl);
    assert.equal(await page.locator('select[name=folder]').inputValue(), receipts);
    await page.goto(url + '/?folder=' + year + '&recursive=1');
    await page.screenshot({ path: path.join(root, 'docs/screenshots/nested-folders.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(root, 'docs/screenshots/nested-folders-mobile.png'), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator('.folder-tile').getByText('电器凭证', { exact: true }).click();
    page.once('dialog', dialog => dialog.accept());
    await navigate(() => page.getByRole('button', { name: '移除文件夹', exact: true }).click());
    assert.equal(folderId(), year);
    assert.equal(await page.getByRole('link', { name: '家用电器购买凭证', exact: true }).count(), 1);
    // Restore the demo so the check is repeatable without losing documents.
    await page.goto(detailUrl);
    await page.locator('select[name=folder]').selectOption(home);
    await navigate(() => page.getByRole('button', { name: '保存修改', exact: true }).click());
    await page.goto(url + '/?folder=' + year);
    page.once('dialog', dialog => dialog.accept());
    await navigate(() => page.getByRole('button', { name: '移除文件夹', exact: true }).click());
    assert.equal(folderId(), work);
    assert.deepEqual(errors, []);
    console.log('Hierarchy browser checks passed: create, breadcrumbs, recursive search, rename, subtree move, identical original, safe removal, mobile navigation.');
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
