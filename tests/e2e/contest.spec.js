import {expect, test} from '@playwright/test';

test.describe('赛事中心', () => {
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

    test('赛事中心页面加载', async ({page}) => {
        await page.goto('/contest_center');
        await expect(page.locator('h2')).toHaveText('赛事中心');
    });

    test('赛事规则页面加载', async ({page}) => {
        await page.goto('/contest/1/rules');
        await expect(page.locator('.rules-container')).toBeVisible();
    });

    test('赛事详情页加载', async ({page}) => {
        await page.goto('/contest/1');
        await expect(page.locator('h2')).toBeVisible();
    });

    test('规则确认后进入赛事', async ({page}) => {
        await page.goto('/contest/1/rules');
        await page.check('#agreeCheckbox');
        await expect(page.locator('#enterBtn')).toHaveCSS('pointer-events', 'auto');
    });
});