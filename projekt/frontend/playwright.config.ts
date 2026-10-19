import { defineConfig } from "@playwright/test";

export default defineConfig({
  workers: 1,
  timeout: 60000,
  testDir: "./e2e",
  use: {
    baseURL: "http://127.0.0.1:15173",
    browserName: "chromium",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command:
        "uv run --project ../backend alembic -c ../backend/alembic.ini upgrade head && uv run --project ../backend uvicorn e2e_app:app --app-dir ../backend/tests --host 127.0.0.1 --port 18000 --timeout-graceful-shutdown 5",
      url: "http://127.0.0.1:18000/health",
      reuseExistingServer: false,
      timeout: 120000,
      env: {
        DATABASE_URL: "sqlite:///./data/e2e.db",
        CORS_ORIGINS: '["http://127.0.0.1:15173"]',
      },
    },
    {
      command: "npx vite --host 127.0.0.1 --port 15173 --strictPort",
      url: "http://127.0.0.1:15173",
      env: { VITE_API_BASE_URL: "http://127.0.0.1:18000" },
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
});
