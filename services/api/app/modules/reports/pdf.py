"""§54 HTML -> PDF via headless Chromium (Playwright is already a dependency
for the JS-render crawler fallback — reused here rather than adding a
second rendering stack like WeasyPrint, whose native GTK deps are painful on
Windows dev machines)."""
from __future__ import annotations


async def render_html_to_pdf(html: str) -> bytes:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            return await page.pdf(format="A4", print_background=True, margin={"top": "0", "bottom": "0"})
        finally:
            await browser.close()
