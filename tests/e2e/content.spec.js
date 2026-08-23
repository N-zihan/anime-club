import {expect, test} from '@playwright/test';

test.describe('内容页面', () => {
    const pages = [
        {path: '/home', title: '首页'},
        {path: '/about', title: '社团简介'},
        {path: '/activities', title: '近期活动'},
        {path: '/gallery', title: '珍贵历史图片'},
        {path: '/anime_resources', title: '番剧资源下载'},
        {path: '/members', title: '社员名单'},
    ];

    for (const p of pages) {
        test(`${p.title}页面加载`, async ({page}) => {
            await page.goto(`http://localhost:5000${p.path}`);
            await expect(page.locator('h1, h2').first()).toBeVisible();
        });
    }
});