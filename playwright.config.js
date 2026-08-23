import {defineConfig, devices} from '@playwright/test';

export default defineConfig({
    testDir: './tests/e2e',
    fullyParallel: false,          // 关闭完全并行
    workers: 1,                    // 只用一个 worker
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    reporter: 'html',
    use: {
        baseURL: 'http://localhost:5000',
        trace: 'on-first-retry',
    },
    projects: [
        {
            name: 'chromium',
            use: {...devices['Desktop Chrome']},
        },
    ],
    webServer: {
        command: 'python run.py',
        url: 'http://localhost:5000',
        reuseExistingServer: !process.env.CI,
        env: {
            TESTING: '1',
            GROUP_VERIFICATION_CODE: 'test_group_code',
            DATABASE_URL: 'sqlite:///:memory:',
        },
    },
});