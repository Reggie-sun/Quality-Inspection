import { expect, test } from "@playwright/test";


test.beforeEach(async ({ page }) => {
  await page.setContent(`
    <main style="width: 186px">
      <div class="inspection-list-controls">
        <label>
          <input
            type="search"
            aria-label="搜索检验项"
            placeholder="搜索检验项"
          />
        </label>
        <label>
          <select aria-label="筛选状态">
            <option>全部状态</option>
          </select>
        </label>
      </div>
      <section class="source-batch-bar" aria-label="待确认来源">
        <strong>138 条待确认来源</strong>
        <button type="button">确认当前有效项</button>
      </section>
    </main>
  `);
  await page.addStyleTag({ path: "src/styles/app.css" });
  await page.addStyleTag({ path: "src/styles/workbench.css" });
});


test("紧凑列表控件使用可完整显示提示的小字号", async ({ page }) => {
  const search = page.getByRole("searchbox", { name: "搜索检验项" });
  await expect(search).toHaveCSS("font-size", "11px");
  await expect(page.getByRole("combobox", { name: "筛选状态" }))
    .toHaveCSS("font-size", "11px");
  expect(await search.evaluate((element) => {
    const input = element as HTMLInputElement;
    const style = getComputedStyle(input);
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (context === null) return false;
    context.font = style.font;
    const availableWidth = input.clientWidth
      - Number.parseFloat(style.paddingLeft)
      - Number.parseFloat(style.paddingRight);
    return context.measureText(input.placeholder).width <= availableWidth;
  })).toBe(true);
});


test("待确认来源提示与操作在窄栏中保持单行", async ({ page }) => {
  const batchBar = page.getByRole("region", { name: "待确认来源" });
  const count = batchBar.getByText("138 条待确认来源");
  const action = batchBar.getByRole("button", { name: "确认当前有效项" });

  await expect(batchBar).toHaveCSS("font-size", "10px");
  await expect(count).toHaveCSS("white-space", "nowrap");
  await expect(action).toHaveCSS("white-space", "nowrap");
  expect((await batchBar.boundingBox())?.height).toBeLessThanOrEqual(46);
  expect(await page.locator("main").evaluate((element) =>
    element.scrollWidth <= element.clientWidth)).toBe(true);
});

test("待确认来源提示在实际紧凑宽度内换行且不撑宽列表", async ({ page }) => {
  await page.locator("main").evaluate((element) => {
    element.style.width = "135px";
  });

  const batchBar = page.getByRole("region", { name: "待确认来源" });
  const countBox = await batchBar.getByText("138 条待确认来源").boundingBox();
  const actionBox = await batchBar
    .getByRole("button", { name: "确认当前有效项" })
    .boundingBox();

  expect(await page.locator("main").evaluate((element) =>
    element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(actionBox?.y).toBeGreaterThan(countBox?.y ?? 0);
});
