import { defineConfig } from '@playwright/test';
import { env } from 'node:process';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  timeout: 180000,
  use: {
    baseURL: 'http://127.0.0.1:8766',
    viewport: { width: 1440, height: 1100 },
    trace: 'retain-on-failure',
    launchOptions: env.EZI_BROWSER ? { executablePath: env.EZI_BROWSER } : {},
  },
  webServer: {
    command: '"backend\\.venv\\Scripts\\python.exe" -m backend.tests.serve_e2e',
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    url: 'http://127.0.0.1:8766/api/status',
    reuseExistingServer: false,
    timeout: 30000,
  },
});
