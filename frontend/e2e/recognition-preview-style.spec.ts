import { expect, test } from "@playwright/test";


test.beforeEach(async ({ page }) => {
  const entries = Array.from({ length: 80 }, (_, index) => `<li>检验项 ${index + 1}</li>`)
    .join("");
  await page.setContent(`
    <main class="product-shell recognition-preview">
      <section class="recognition-preview__summary">
        <div><h1>识别预览</h1></div>
        <span class="recognition-preview__version">版本 1</span>
        <ul class="recognition-preview__metrics"><li>本地已解析：80</li></ul>
      </section>
      <div class="recognition-preview__layout">
        <section class="recognition-preview__drawing"><iframe title="工程图纸预览"></iframe></section>
        <aside class="recognition-preview__results">
          <section><ul>${entries}</ul></section>
          <section><ul>${entries}</ul></section>
        </aside>
      </div>
    </main>
  `);
  await page.addStyleTag({ path: "src/styles/app.css" });
  await page.addStyleTag({ path: "src/styles/recognition-preview.css" });
});


test("识别预览在桌面宽度保持大图纸区和独立滚动结果栏", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });

  const geometry = await page.evaluate(() => {
    const main = document.querySelector<HTMLElement>(".recognition-preview")!;
    const layout = document.querySelector<HTMLElement>(".recognition-preview__layout")!;
    const iframe = document.querySelector<HTMLIFrameElement>(".recognition-preview__drawing iframe")!;
    const resultLists = [...document.querySelectorAll<HTMLElement>(".recognition-preview__results ul")];
    return {
      noHorizontalOverflow: main.scrollWidth <= main.clientWidth
        && layout.scrollWidth <= layout.clientWidth,
      columns: getComputedStyle(layout).gridTemplateColumns.split(" ").length,
      iframeWidth: iframe.clientWidth,
      iframeHeight: iframe.clientHeight,
      resultLists: resultLists.map((list) => ({
        scrollable: list.scrollHeight > list.clientHeight,
        overflowY: getComputedStyle(list).overflowY,
      })),
    };
  });

  expect(geometry.noHorizontalOverflow).toBe(true);
  expect(geometry.columns).toBe(2);
  expect(geometry.iframeWidth).toBeGreaterThan(700);
  expect(geometry.iframeHeight).toBeGreaterThanOrEqual(500);
  expect(geometry.resultLists).toEqual([
    { scrollable: true, overflowY: "auto" },
    { scrollable: true, overflowY: "auto" },
  ]);
});


test("识别预览在窄屏收敛为无横向溢出的单栏", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 });

  const geometry = await page.evaluate(() => {
    const main = document.querySelector<HTMLElement>(".recognition-preview")!;
    const layout = document.querySelector<HTMLElement>(".recognition-preview__layout")!;
    const iframe = document.querySelector<HTMLIFrameElement>(".recognition-preview__drawing iframe")!;
    return {
      noHorizontalOverflow: main.scrollWidth <= main.clientWidth
        && layout.scrollWidth <= layout.clientWidth,
      columns: getComputedStyle(layout).gridTemplateColumns.split(" ").length,
      iframeWidth: iframe.clientWidth,
    };
  });

  expect(geometry.noHorizontalOverflow).toBe(true);
  expect(geometry.columns).toBe(1);
  expect(geometry.iframeWidth).toBeGreaterThan(650);
});
