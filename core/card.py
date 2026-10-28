"""把小黑盒数据整理成卡片结构，并生成 HTML（参照小黑盒游戏页排版）。"""
from __future__ import annotations

import html
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SaleSegment:
    start: str
    end: str
    days: int
    price: str
    discount: int


@dataclass
class StatCell:
    label: str
    value: str


@dataclass
class CardData:
    appid: int
    name: str
    name_en: str = ""
    cover: str = ""
    score: str = ""
    score_count: str = ""
    price_now: str = ""
    price_old: str = ""
    discount: int = 0
    is_free: bool = False
    platforms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    stats: list[StatCell] = field(default_factory=list)
    release: str = ""
    developers: str = ""
    publishers: str = ""
    req_minimum: str = ""
    req_recommended: str = ""
    intro: str = ""
    sales: list[SaleSegment] = field(default_factory=list)
    regions: list[dict[str, Any]] = field(default_factory=list)
    lowest_price: str = ""
    lowest_date: str = ""
    lowest_discount: int = 0
    lowest_count: int = 0


def _fmt_wan(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    if text in ("-", "N/A"):
        return "-"
    if not text.replace(".", "", 1).isdigit():
        return text
    return f"{text} 万"


def _date_from_epoch(value: Any) -> str:
    try:
        ts = int(str(value))
    except (TypeError, ValueError):
        return str(value or "")
    if ts > 10_000_000_000:
        ts //= 1000
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _menu_value(menu: list[dict[str, Any]], key: str) -> str:
    for item in menu or []:
        if isinstance(item, dict) and item.get("type") == key:
            return str(item.get("value") or "").strip()
    return ""


def build_sales(prices: list[dict[str, Any]], limit: int = 3) -> list[SaleSegment]:
    """小黑盒的历史价格是按变动事件记录的：discount>0 的一条 = 一次促销开始。"""
    events: list[SaleSegment] = []
    entries = [p for p in prices if isinstance(p, dict)]

    def ts(entry: dict[str, Any]) -> int:
        try:
            value = int(str(entry.get("date")))
        except (TypeError, ValueError):
            return 0
        return value // 1000 if value > 10_000_000_000 else value

    now = int(time.time())
    for index, entry in enumerate(entries):
        try:
            discount = int(entry.get("discount") or 0)
        except (TypeError, ValueError):
            discount = 0
        if discount <= 0:
            continue
        begin = ts(entry)
        if begin <= 0:
            continue
        finish = ts(entries[index + 1]) if index + 1 < len(entries) else now
        finish = finish or now
        events.append(
            SaleSegment(
                start=datetime.fromtimestamp(begin).strftime("%Y-%m-%d"),
                end=datetime.fromtimestamp(finish).strftime("%Y-%m-%d"),
                days=max(1, round((finish - begin) / 86400)),
                price=str(entry.get("price") or ""),
                discount=discount,
            )
        )
    return events[-limit:]


def build_card(
    detail: dict[str, Any],
    history: dict[str, Any] | None = None,
    regions: list[dict[str, Any]] | None = None,
    requirements: dict[str, Any] | None = None,
    max_regions: int = 5,
    max_tags: int = 8,
    intro_length: int = 120,
) -> CardData:
    detail = detail or {}
    price = detail.get("price") or {}
    menu = detail.get("menu_v2") or []

    try:
        discount = int(price.get("discount") or 0)
    except (TypeError, ValueError):
        discount = 0

    card = CardData(
        appid=int(detail.get("steam_appid") or detail.get("appid") or 0),
        name=str(detail.get("name") or ""),
        name_en=str(detail.get("name_en") or ""),
        cover=str(detail.get("image") or detail.get("appicon") or ""),
        score=str(detail.get("score") or ""),
        price_now=str(price.get("current") or ""),
        price_old=str(price.get("initial") or ""),
        discount=discount,
        is_free=bool(detail.get("is_free")),
        release=_menu_value(menu, "release_date"),
        developers=_menu_value(menu, "developer"),
        publishers=_menu_value(menu, "publisher"),
    )

    comment_stats = detail.get("comment_stats") or {}
    if isinstance(comment_stats, dict):
        count = comment_stats.get("score_comment")
        if count:
            card.score_count = f"{int(count):,}"

    platforms = detail.get("platforms_list") or []
    names = [str(p.get("name") or "") for p in platforms if isinstance(p, dict)]
    card.platforms = [n for n in names if n][:4]

    tags = []
    for tag in detail.get("common_tags") or []:
        if isinstance(tag, dict) and tag.get("desc"):
            tags.append(str(tag["desc"]))
    card.tags = tags[:max_tags]

    # 数据格：小黑盒游戏页的 user_num.game_data
    user_num = detail.get("user_num") or {}
    for item in user_num.get("game_data") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("desc") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label:
            continue
        if label in ("当前在线", "昨日峰值在线", "小黑盒玩家数"):
            value = _fmt_wan(value)
        card.stats.append(StatCell(label=label, value=value or "-"))
    card.stats = card.stats[:8]

    history = history or {}
    lowest = history.get("lowest_info") or {}
    lowest_v2 = history.get("lowest_info_v2") or {}
    if isinstance(lowest, dict) and lowest:
        card.lowest_price = str(lowest.get("price") or "")
        card.lowest_date = str(lowest.get("date") or "")
        try:
            card.lowest_discount = int(lowest.get("discount") or 0)
        except (TypeError, ValueError):
            card.lowest_discount = 0
    else:
        card.lowest_price = str(price.get("lowest_price") or "")
    if isinstance(lowest_v2, dict):
        try:
            card.lowest_count = int(lowest_v2.get("count") or 0)
        except (TypeError, ValueError):
            card.lowest_count = 0
    card.sales = build_sales(history.get("prices") or [])

    req = requirements or {}
    card.req_minimum = str(req.get("minimum") or "")
    card.req_recommended = str(req.get("recommended") or "")
    if not card.developers:
        card.developers = ", ".join(req.get("developers") or [])
    if not card.publishers:
        card.publishers = ", ".join(req.get("publishers") or [])
    if not card.release:
        card.release = str(req.get("release_date") or "")

    intro = str(detail.get("about_the_game") or "").strip()
    intro = " ".join(intro.split())
    if intro_length > 0 and len(intro) > intro_length:
        intro = intro[:intro_length].rstrip() + "…"
    card.intro = intro

    items = []
    for region in (regions or []):
        try:
            price_cny = float(region.get("current") or 0)
        except (TypeError, ValueError):
            continue
        if price_cny <= 0:
            continue
        items.append({
            "name": str(region.get("name") or ""),
            "cc": str(region.get("cc") or "").upper(),
            "price": f"{price_cny:.0f}",
        })
    items.sort(key=lambda x: float(x["price"]))
    card.regions = items[:max_regions]
    return card


CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { background:transparent; font-family:'WenQuanYi Zen Hei','Noto Sans CJK SC',sans-serif; }
#card { width:760px; background:#17191e; color:#e9eef6; border-radius:18px; overflow:hidden;
        border:1px solid #262b34; }
.cover { width:100%; aspect-ratio:16/9; object-fit:cover; display:block; background:#0f1116; }
.body { padding:20px 22px 18px; }
.pricebar { display:flex; align-items:center; justify-content:space-between;
            background:#22262e; border-radius:10px; padding:14px 18px; margin-bottom:16px; }
.price-now { font-size:34px; font-weight:700; color:#fff; }
.price-old { font-size:15px; color:#8a95a6; text-decoration:line-through; margin-left:12px; }
.badge { font-size:14px; font-weight:700; color:#fff; background:#e5484d; padding:2px 8px;
         border-radius:6px; margin-left:10px; }
.trend { font-size:13px; color:#9aa6b8; }
.title-row { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.title { font-size:32px; font-weight:700; line-height:1.2; }
.title-en { font-size:14px; color:#8794a8; margin-top:6px; }
.scorebox { background:#f08a24; border-radius:10px; padding:8px 14px; text-align:center; flex:none; }
.scorebox .s { font-size:26px; font-weight:700; color:#fff; line-height:1; }
.scorebox .c { font-size:11px; color:#fff9; margin-top:4px; }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
.chip { font-size:13px; color:#c8d3e2; background:#22262e; border:1px solid #2e3540;
        padding:5px 12px; border-radius:7px; }
.chip.plat { color:#fff; background:#2a3340; }
.grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:16px; }
.cell { background:#1d2129; border-radius:10px; padding:12px 10px; text-align:center; }
.cell .v { font-size:19px; font-weight:700; color:#e9eef6; }
.cell .l { font-size:12px; color:#7f8da2; margin-top:5px; }
.meta { margin-top:14px; background:#1d2129; border-radius:10px; padding:14px 16px; }
.meta .row { display:flex; font-size:14px; padding:4px 0; }
.meta .k { width:76px; color:#7f8da2; flex:none; }
.meta .v { color:#dfe7f2; }
.req { margin-top:12px; background:#1d2129; border-radius:10px; padding:14px 16px; }
.req h4 { font-size:13px; color:#7f8da2; font-weight:600; margin-bottom:8px; letter-spacing:1px; }
.req p { font-size:13.5px; color:#d6dfec; line-height:1.7; white-space:pre-wrap; }
.req .none { color:#6d7889; }
.intro { margin-top:12px; font-size:13.5px; color:#aab6c8; line-height:1.75; }
.footer { display:flex; justify-content:space-between; font-size:12px; color:#5e6a7c;
          margin-top:16px; padding-top:12px; border-top:1px solid #262b34; }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def render_html(card: CardData) -> str:
    if card.is_free:
        price_html = '<span class="price-now">免费</span>'
    else:
        price_html = f'<span class="price-now">¥{_esc(card.price_now or "-")}</span>'
        if card.price_old and card.price_old != card.price_now:
            price_html += f'<span class="price-old">¥{_esc(card.price_old)}</span>'
        if card.discount > 0:
            price_html += f'<span class="badge">-{card.discount}%</span>'

    chips = "".join(f'<span class="chip plat">{_esc(p)}</span>' for p in card.platforms)
    chips += "".join(f'<span class="chip">{_esc(t)}</span>' for t in card.tags)

    cells = "".join(
        f'<div class="cell"><div class="v">{_esc(c.value)}</div><div class="l">{_esc(c.label)}</div></div>'
        for c in card.stats
    )

    meta_rows = []
    if card.release:
        meta_rows.append(f'<div class="row"><span class="k">发布时间</span><span class="v">{_esc(card.release)}</span></div>')
    if card.developers:
        meta_rows.append(f'<div class="row"><span class="k">开发商</span><span class="v">{_esc(card.developers)}</span></div>')
    if card.publishers:
        meta_rows.append(f'<div class="row"><span class="k">发行商</span><span class="v">{_esc(card.publishers)}</span></div>')
    meta_html = f'<div class="meta">{"".join(meta_rows)}</div>' if meta_rows else ""

    if card.req_minimum or card.req_recommended:
        req_body = ""
        if card.req_minimum:
            req_body += f'<p><b style="color:#9fb0c7">最低配置</b><br>{_esc(card.req_minimum)}</p>'
        if card.req_recommended:
            req_body += f'<p style="margin-top:10px"><b style="color:#9fb0c7">推荐配置</b><br>{_esc(card.req_recommended)}</p>'
        req_html = f'<div class="req"><h4>配置要求</h4>{req_body}</div>'
    else:
        req_html = '<div class="req"><h4>配置要求</h4><p class="none">暂无数据（Steam 商店接口在本机不可达）</p></div>'

    intro_html = f'<div class="intro">{_esc(card.intro)}</div>' if card.intro else ""
    score_html = (
        f'<div class="scorebox"><div class="s">{_esc(card.score)}</div>'
        f'<div class="c">{_esc(card.score_count + " 人评分") if card.score_count else "评分"}</div></div>'
        if card.score else ""
    )
    cover_html = f'<img class="cover" src="{_esc(card.cover)}" />' if card.cover else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body><div id="card">
  {cover_html}
  <div class="body">
    <div class="pricebar">{price_html}<span class="trend">全区价格 / 史低 ¥{_esc(card.lowest_price or "-")}</span></div>
    <div class="title-row">
      <div><div class="title">{_esc(card.name)}</div><div class="title-en">{_esc(card.name_en)}</div></div>
      {score_html}
    </div>
    <div class="chips">{chips}</div>
    <div class="grid">{cells}</div>
    {meta_html}
    {req_html}
    {intro_html}
    <div class="footer"><span>数据来源：小黑盒</span><span>{time.strftime('%Y-%m-%d %H:%M')}</span></div>
  </div>
</div></body></html>"""
