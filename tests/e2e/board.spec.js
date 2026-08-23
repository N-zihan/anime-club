import {expect, test} from '@playwright/test';

test.describe('留言板', () => {
    test.beforeEach(async ({page}) => {
        // 尝试注册（用户可能已存在，忽略错误）
        await page.goto('/register');
        await page.fill('input[name="username"]', 'testuser');
        await page.fill('input[name="qq"]', '123456789');
        await page.fill('input[name="email"]', 'test@qq.com');
        await page.fill('input[name="code"]', '123456');
        await page.fill('input[name="group"]', 'test_group_code');
        await page.fill('input[name="password"]', 'password123');
        await page.click('button[type="submit"]');
        // 无论注册是否成功，都去登录
        await page.goto('/login');
        await page.fill('input[name="username"]', 'testuser');
        await page.fill('input[name="password"]', 'password123');
        await page.click('button[type="submit"]');
        await expect(page.locator('.user-name')).toBeVisible();
    });

    test('留言板页面加载', async ({page}) => {
        await page.goto('/board');
        await expect(page.locator('h2')).toHaveText('社员留言板');
    });

    test('发表留言', async ({page}) => {
        await page.goto('/board');
        await page.fill('textarea[name="content"]', '这是一条测试留言');
        await page.click('.new-msg-submit');
        await expect(page.locator('.message-body')).toContainText('测试留言');
    });
});