const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "frontend-tests",
  use: {
    baseURL: "http://127.0.0.1:8765",
    browserName: "chromium",
  },
  projects: [
    {
      name: "desktop",
      use: { colorScheme: "light", viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "mobile",
      use: { colorScheme: "light", viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: {
    command: "python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765",
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
  },
});
