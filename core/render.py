"""HTML → PNG（playwright / chromium）。"""
from __future__ import annotations

import os
import tempfile


class RenderError(RuntimeError):
    pass


def _trim_transparent(path: str) -> None:
    """裁掉透明留白：元素截图偶尔会带出视口大小的空白区。"""
    try:
        from PIL import Image
    except ImportError:
        return
    try:
        with Image.open(path) as im:
            if im.mode != "RGBA":
                return
            bbox = im.getchannel("A").getbbox()
            if not bbox:
                return
            if bbox != (0, 0, im.width, im.height):
                im.crop(bbox).save(path)
    except Exception:  # noqa: BLE001
        pass


async def render_png(html: str, width: int = 760, scale: float = 2.0, timeout_ms: int = 30000) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # noqa: BLE001
        raise RenderError("未安装 playwright，无法渲染图片") from exc

    fd, path = tempfile.mkstemp(prefix="heybox_card_", suffix=".png")
    os.close(fd)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--font-render-hinting=none",
                    "--hide-scrollbars",
                ],
            )
            try:
                page = await browser.new_page(
                    viewport={"width": width + 4, "height": 900},
                    device_scale_factor=max(1.0, float(scale)),
                )
                await page.set_content(html, wait_until="load", timeout=timeout_ms)
                # 等封面图、字体就位
                await page.wait_for_timeout(1200)
                card = await page.query_selector("#card, #price-card")
                if card is not None:
                    # omit_background=True 保留圆角透明，输出带 alpha 的 PNG
                    await card.screenshot(path=path, omit_background=True)
                else:
                    await page.screenshot(path=path, full_page=True, omit_background=True)
            finally:
                await browser.close()
        _trim_transparent(path)
    except RenderError:
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            os.unlink(path)
        except OSError:
            pass
        raise RenderError(f"{type(exc).__name__}: {exc}") from exc
    return path
