"""小黑盒游戏卡片插件。

输入游戏名 / appid / 小黑盒或 Steam 游戏链接 → 抓小黑盒数据 → 绘制卡片图。
只处理游戏相关链接，其它链接一律不响应。
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.star.filter.command import GreedyStr

from .core.api import HeyboxAPI, HeyboxError, extract_appid, pick_game
from .core.card import build_card, render_html
from .core.login import LoginState, XiaoheiheLoginClient, generate_qr_png
from .core.render import RenderError, render_png

PLUGIN_NAME = "astrbot_plugin_heybox_game"
PLUGIN_VERSION = "1.0.0"
PLUGIN_REPOSITORY = "https://github.com/dahaoiua/astrbot_plugin_heybox_game"
PLUGIN_DESCRIPTION = "输入游戏名 / appid / 链接，抓取小黑盒数据并绘制成卡片图片。"

LINK_HINT = (
    "只支持这几种输入：\n"
    "· 游戏名：/小黑盒 赛博朋克2077\n"
    "· appid：/小黑盒 1091500\n"
    "· 小黑盒游戏链接：https://www.xiaoheihe.cn/app/topic/game/pc/1091500\n"
    "· Steam 商店链接：https://store.steampowered.com/app/1091500/"
)


@register(
    PLUGIN_NAME,
    "dahaoiua",
    PLUGIN_DESCRIPTION,
    PLUGIN_VERSION,
    PLUGIN_REPOSITORY,
)
class HeyboxGamePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        try:
            self.data_dir: Path = StarTools.get_data_dir(PLUGIN_NAME)
        except Exception:  # noqa: BLE001
            self.data_dir = Path(__file__).parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cred_file = self.data_dir / "credentials.json"
        self._login_tasks: dict[str, asyncio.Task] = {}

    # ---------------- 配置与凭证 ----------------

    def _cfg(self, key: str, default: Any) -> Any:
        value = self.config.get(key, default)
        if isinstance(value, dict) and "data" in value:
            return value["data"]
        return value if value is not None else default

    def _credentials(self) -> dict[str, Any]:
        try:
            return json.loads(self.cred_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save_credentials(self, cookies: dict[str, str], uid: str, nickname: str) -> None:
        payload = {
            "cookies": cookies,
            "uid": uid,
            "nickname": nickname,
            "logged_in_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.cred_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cookie_header(self) -> str:
        """配置里的 cookie 优先，其次扫码登录保存下来的。"""
        raw = str(self._cfg("cookies", "") or "").strip()
        if raw:
            return raw
        cookies = self._credentials().get("cookies") or {}
        parts = [f"{k}={v}" for k, v in cookies.items() if v]
        return "; ".join(parts)

    def _api(self) -> HeyboxAPI:
        return HeyboxAPI(
            self._cookie_header(),
            int(self._cfg("timeout", 20)),
            str(self._cfg("proxy", "") or ""),
        )

    # ---------------- 查询 ----------------

    async def _resolve(self, api: HeyboxAPI, text: str) -> dict[str, Any]:
        appid = extract_appid(text)
        if appid is not None:
            games = await api.search(str(appid))
            for game in games:
                try:
                    if int(game.get("steam_appid") or 0) == appid:
                        return game
                except (TypeError, ValueError):
                    continue
            # 搜不到精确匹配时用最小结构兜底，后续仍能查价格
            return {"steam_appid": appid, "name": f"appid={appid}"}

        games = await api.search(text.strip())
        game = pick_game(games, text.strip())
        if game is None:
            raise HeyboxError("小黑盒没有搜到这个游戏")
        return game

    @filter.command("小黑盒", alias={"xhh", "游戏价格", "steamprice", "查价"})
    async def heybox_query(self, event: AstrMessageEvent, query: GreedyStr):
        """查询游戏价格并生成卡片图。"""
        text = str(query or "").strip()
        if not text:
            yield event.plain_result("用法：/小黑盒 游戏名 或 /小黑盒 appid 或 直接发游戏链接\n\n" + LINK_HINT)
            return
        if "http" in text and extract_appid(text) is None:
            yield event.plain_result("这个链接不是游戏分享链接，我只解析游戏相关链接。\n\n" + LINK_HINT)
            return

        api = self._api()
        try:
            game = await self._resolve(api, text)
            appid = int(game.get("steam_appid") or game.get("appid") or 0)
            detail: dict[str, Any] = {}
            try:
                detail = await api.detail(appid)
            except HeyboxError as exc:
                logger.warning(f"[heybox] 详情获取失败 appid={appid}: {exc}")
            if not detail:
                # 详情失败时用搜索结果兜底，至少能出价格
                detail = {
                    "steam_appid": appid,
                    "name": game.get("name") or f"appid={appid}",
                    "image": game.get("head_image_616_353") or game.get("image") or "",
                    "score": game.get("score") or "",
                    "price": game.get("price") or {},
                    "common_tags": [{"desc": game.get("core_tags_str") or ""}],
                }
            days = int(self._cfg("days", 720))
            history: dict[str, Any] = {}
            regions: list[dict[str, Any]] = []
            try:
                history = await api.history(appid, days)
            except HeyboxError as exc:
                logger.warning(f"[heybox] 历史价格获取失败 appid={appid}: {exc}")
            try:
                regions = await api.global_prices(appid)
            except HeyboxError as exc:
                logger.warning(f"[heybox] 跨区价格获取失败 appid={appid}: {exc}")

            requirements: dict[str, Any] = {}
            if bool(self._cfg("show_requirements", True)):
                try:
                    requirements = await api.hardware_requirements(appid)
                except HeyboxError as exc:
                    logger.warning(f"[heybox] 配置要求获取失败 appid={appid}: {exc}")
                if not requirements and bool(self._cfg("steam_requirements", False)):
                    steam = await api.steam_requirements(
                        appid, float(self._cfg("requirements_timeout", 4))
                    )
                    if steam:
                        requirements = {
                            "minimum": [("", steam.get("minimum") or "")],
                            "recommended": [("", steam.get("recommended") or "")],
                        }
            card = build_card(
                detail,
                history,
                regions,
                requirements,
                int(self._cfg("max_regions", 5)),
                int(self._cfg("max_tags", 8)),
                int(self._cfg("intro_length", 120)),
            )
            html = render_html(card)
            png = await render_png(html, int(self._cfg("render_width", 760)), float(self._cfg("render_scale", 2.0)))
            cache_dir = self.data_dir / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            keep = cache_dir / f"card_{appid}_{int(time.time())}.png"
            os.replace(png, keep)
            png = str(keep)
            self._clean_cache(cache_dir, int(self._cfg("cache_keep_seconds", 3600)))
        except HeyboxError as exc:
            yield event.plain_result(f"查询失败：{exc}")
            return
        except RenderError as exc:
            yield event.plain_result(f"图片渲染失败：{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("heybox card failed")
            yield event.plain_result(f"查询失败：{type(exc).__name__}: {exc}")
            return

        yield event.image_result(png)

    def _clean_cache(self, cache_dir: Path, keep_seconds: int = 3600) -> None:
        """删掉一小时前的卡片，避免堆积。"""
        deadline = time.time() - keep_seconds
        for item in cache_dir.glob("card_*.png"):
            try:
                if item.stat().st_mtime < deadline:
                    item.unlink()
            except OSError:
                pass

    # ---------------- 扫码登录 ----------------

    @filter.command("小黑盒登录", alias={"xhh登录"})
    async def heybox_login(self, event: AstrMessageEvent):
        """扫码登录小黑盒（cookie 用于更稳定的数据抓取）。"""
        if bool(self._cfg("admin_only_login", True)) and not event.is_admin():
            yield event.plain_result("只有管理员可以触发扫码登录。")
            return

        client = XiaoheiheLoginClient()
        try:
            session = await client.request_qr()
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(f"获取二维码失败：{exc}")
            return

        cache_dir = self.data_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        qr_path = cache_dir / f"login_{int(time.time())}.png"
        qr_path.write_bytes(generate_qr_png(session.qr_content))
        yield event.image_result(str(qr_path))
        yield event.plain_result("请用小黑盒 APP 扫码，60 秒内有效。")

        deadline = time.time() + 90
        last_state = None
        while time.time() < deadline:
            await asyncio.sleep(3)
            try:
                result = await client.check_qr(session)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[heybox] 轮询登录状态失败：{exc}")
                continue
            if result.state != last_state:
                last_state = result.state
                if result.state == LoginState.SCANNED_WAITING_CONFIRM:
                    yield event.plain_result("已扫码，请在手机上确认登录。")
            if result.state == LoginState.SUCCESS:
                self._save_credentials(result.cookies, result.uid, result.nickname)
                logger.info(f"[heybox] 登录成功 uid={result.uid}")
                yield event.plain_result(
                    f"登录成功：{result.nickname or result.uid}（cookie 已保存，后续查询会自动使用）"
                )
                return
            if result.state in (LoginState.EXPIRED, LoginState.FAILED):
                yield event.plain_result(f"登录未完成：{result.message or result.state.value}")
                return

        yield event.plain_result("二维码已过期，请重新发送 /小黑盒登录")

    @filter.command("小黑盒状态", alias={"xhh状态"})
    async def heybox_status(self, event: AstrMessageEvent):
        """查看当前 cookie / 登录状态。"""
        cred = self._credentials()
        configured = bool(str(self._cfg("cookies", "") or "").strip())
        lines = [
            f"· 配置里的 cookie：{'已填写' if configured else '未填写'}",
            f"· 扫码登录保存的 cookie：{'有' if cred.get('cookies') else '无'}",
        ]
        if cred:
            lines.append(f"· 账号：{cred.get('nickname') or '-'}（uid {cred.get('uid') or '-'}）")
            lines.append(f"· 登录时间：{cred.get('logged_in_at') or '-'}")
        lines.append(f"· 实际生效：{'有 cookie' if self._cookie_header() else '无 cookie（仅公开数据）'}")
        yield event.plain_result("\n".join(lines))
