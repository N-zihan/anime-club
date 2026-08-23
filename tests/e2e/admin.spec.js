import {expect, test} from '@playwright/test';

test.describe('后台管理', () => {
    test.beforeEach(async ({page}) => {
        await page.goto('/login');
        await page.fill('input[name="username"]', 'testuser');
        await page.fill('input[name="password"]', 'password123');
        await page.click('button[type="submit"]');
        await expect(page.locator('.user-name')).toBeVisible();
    });

    test('站长面板加载', async ({page}) => {
        await page.goto('/admin/dashboard');
        await expect(page.locator('h2')).toHaveText('站长管理面板');
    });

    test('运营面板加载', async ({page}) => {
        await page.goto('/staff/dashboard');
        await expect(page.locator('h2')).toHaveText('运营管理面板');
    });

    test('活动管理加载', async ({page}) => {
        await page.goto('/admin/activities');
        await expect(page.locator('h2')).toHaveText('活动管理');
    });

    test('番剧资源管理加载', async ({page}) => {
        await page.goto('/admin/anime_resources');
        await expect(page.locator('h2')).toHaveText('番剧资源管理');
    });

    test('照片墙管理加载', async ({page}) => {
        await page.goto('/admin/gallery');
        await expect(page.locator('h2')).toHaveText('照片墙管理');
    });

    test('用户管理加载', async ({page}) => {
        await page.goto('/admin/users');
        await expect(page.locator('h2')).toHaveText('用户管理');
    });

    test('留言管理加载', async ({page}) => {
        await page.goto('/admin/messages');
        await expect(page.locator('h2')).toHaveText('留言管理');
    });

    test('赛事管理加载', async ({page}) => {
        await page.goto('/admin/contests/manage');
        await expect(page.locator('h2')).toHaveText('赛事管理');
    });

    test('赛事编辑页加载', async ({page}) => {
        await page.goto('/admin/contests/edit/1');
        await expect(page.locator('h2')).toContainText('编辑赛事');
    });
});