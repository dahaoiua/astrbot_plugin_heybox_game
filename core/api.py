"""小黑盒公开接口封装。

只用到三个接口（都是公开的，带 cookie 时频率限制更宽松）：
  /game/search/                        游戏搜索：appid、名称、价格、评分、在线、关注、标签、封面
  /game/get_game_prices/history/v2     历史价格：每日价格 + 史低
  /game/get_game_global_prices/        跨区价格

注意：history 接口的 cc 必须小写（cn），传 CN 会返回空 result。
"""
from __future__ import annotations

import html as html_module
import re
from typing import Any

import aiohttp

from .login import WEB_CLIENT_PARAMS, _sign_params

BASE = "https://api.xiaoheihe.cn"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# 支持的游戏链接（只认这些，其它链接一律不处理）
XHH_GAME_RE = re.compile(r"https?://(?:www\.)?xiaoheihe\.cn/app/topic/game/pc/(\d+)", re.I)
STEAM_APP_RE = re.compile(r"https?://store\.steampowered\.com/app/(\d+)", re.I)


class HeyboxError(RuntimeError):
    pass


def extract_appid(text: str) -> int | None:
    """从链接或纯数字里取 appid。"""
    text = (text or "").strip()
    for pattern in (XHH_GAME_RE, STEAM_APP_RE):
        m = pattern.search(text)
        if m:
            return int(m.group(1))
    if text.isdigit():
        return int(text)
    return None


def normalize_name(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (value or "").casefold())


def pick_game(games: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    """从搜索结果里挑最匹配的一个。"""
    if not games:
        return None
    key = normalize_name(query)
    exact = [g for g in games if normalize_name(str(g.get("name") or "")) == key]
    if exact:
        return exact[0]
    prefix = [g for g in games if normalize_name(str(g.get("name") or "")).startswith(key)]
    if prefix:
        return prefix[0]
    contain = [g for g in games if key and key in normalize_name(str(g.get("name") or ""))]
    if contain:
        return contain[0]
    return games[0]


def _strip_html(value: str) -> str:
    """Steam 的配置要求是 HTML 片段，转成纯文本。"""
    text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_module.unescape(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "；".join(lines[:8])


class HeyboxAPI:
    def __init__(self, cookie: str = "", timeout: int = 20, proxy: str = "") -> None:
        self.cookie = (cookie or "").strip()
        self.timeout = timeout
        self.proxy = (proxy or "").strip()

    def _headers(self, appid: int | None = None) -> dict[str, str]:
        referer = "https://www.xiaoheihe.cn/"
        if appid:
            referer = f"https://www.xiaoheihe.cn/app/topic/game/pc/{appid}"
        headers = {
            "User-Agent": UA,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer,
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    async def _get(self, path: str, params: dict[str, Any], appid: int | None = None) -> dict[str, Any]:
        url = BASE + path
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    url, params=params, headers=self._headers(appid),
                    proxy=self.proxy or None,
                ) as resp:
                    if resp.status != 200:
                        raise HeyboxError(f"HTTP {resp.status}: {path}")
                    payload = await resp.json(content_type=None)
        except HeyboxError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HeyboxError(f"{type(exc).__name__}: {exc}") from exc
        if not isinstance(payload, dict):
            raise HeyboxError("返回格式异常")
        return payload

    async def detail(self, appid: int) -> dict[str, Any]:
        """游戏详情（需要签名）：名称、评分、标签、价格、统计数据、发布时间/开发商/发行商。"""
        params = _sign_params(
            "/game/get_game_detail/",
            {**WEB_CLIENT_PARAMS, "steam_appid": str(appid)},
            "",
        )
        data = await self._get("/game/get_game_detail/", params, appid)
        result = data.get("result")
        return result if isinstance(result, dict) else {}

    async def steam_requirements(self, appid: int, timeout: float = 4.0) -> dict[str, Any]:
        """尽力从 Steam 拿配置要求；本机通常不可达，超时就直接放弃。"""
        url = "https://store.steampowered.com/api/appdetails"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                async with session.get(
                    url,
                    params={"appids": appid, "l": "schinese", "cc": "cn"},
                    proxy=self.proxy or None,
                ) as resp:
                    if resp.status != 200:
                        return {}
                    payload = await resp.json(content_type=None)
        except Exception:  # noqa: BLE001
            return {}
        entry = (payload or {}).get(str(appid)) or {}
        if not entry.get("success"):
            return {}
        data = entry.get("data") or {}
        req = data.get("pc_requirements") or {}
        return {
            "minimum": _strip_html(req.get("minimum") or ""),
            "recommended": _strip_html(req.get("recommended") or ""),
            "developers": data.get("developers") or [],
            "publishers": data.get("publishers") or [],
            "release_date": (data.get("release_date") or {}).get("date", ""),
        }

    async def search(self, query: str) -> list[dict[str, Any]]:
        data = await self._get("/game/search/", {"q": query, "lang": "zh-cn", "os_type": "web"})
        result = data.get("result") or {}
        games = result.get("games") if isinstance(result, dict) else None
        return [g for g in (games or []) if isinstance(g, dict)]

    async def history(self, appid: int, days: int = 720) -> dict[str, Any]:
        data = await self._get(
            "/game/get_game_prices/history/v2",
            {"appid": appid, "platf": "steam", "cc": "cn", "days": days},
            appid,
        )
        result = data.get("result")
        return result if isinstance(result, dict) else {}

    async def global_prices(self, appid: int) -> list[dict[str, Any]]:
        data = await self._get(
            "/game/get_game_global_prices/",
            {"lang": "zh-cn", "os_type": "web", "offset": 0, "limit": 100, "steam_appid": appid},
            appid,
        )
        result = data.get("result") or {}
        prices = result.get("prices") if isinstance(result, dict) else None
        return [p for p in (prices or []) if isinstance(p, dict)]
