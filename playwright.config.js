const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "frontend-tests",
  use: {
    baseURL: "http://127.0.0.1:8765",
    browserName: "chromium",
  },
  projects: [
    { name: "light", use: { colorScheme: "light" } },
    { name: "dark", use: { colorScheme: "dark" } },
  ],
  webServer: {
    command: "python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765",
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
  },
});
