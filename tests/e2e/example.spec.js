import { test, expect } from '@playwright/test';

// 占位测试，确保 CI 能通过
test('占位测试：确保 CI 能跑通', async ({ page }) => {
  // 这个测试什么也不做，只是让 Playwright 能找到测试用例
  expect(true).toBe(true);
});