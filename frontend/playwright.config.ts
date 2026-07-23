import { defineConfig } from "@playwright/test";


const reportDirectory = process.env.QI_P0_REPORT_DIR;
const sampleOrder = process.env.QI_P0_SAMPLE_ORDER ?? "local";
const phase = process.env.QI_P0_E2E_PHASE ?? "local";


export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  outputDir: reportDirectory === undefined
    ? "test-results"
    : `${reportDirectory}/playwright-output-${sampleOrder}-${phase}`,
  reporter: reportDirectory === undefined
    ? [["list"]]
    : [["json", { outputFile: `${reportDirectory}/playwright-${sampleOrder}-${phase}.json` }]],
  use: {
    channel: "chrome",
    viewport: { width: 1565, height: 796 },
    deviceScaleFactor: 1,
    colorScheme: "light",
    locale: "en-US",
    timezoneId: "Asia/Hong_Kong",
    trace: "retain-on-failure",
  },
});
