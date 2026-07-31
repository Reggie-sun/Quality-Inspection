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
