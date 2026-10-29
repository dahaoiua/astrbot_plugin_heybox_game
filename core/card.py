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
    req_min: list[tuple[str, str]] = field(default_factory=list)
    req_rec: list[tuple[str, str]] = field(default_factory=list)
    intro: str = ""
    sales: list[SaleSegment] = field(default_factory=list)
    regions: list[dict[str, Any]] = field(default_factory=list)
    lowest_price: str = ""
    lowest_date: str = ""
    lowest_discount: int = 0
    lowest_count: int = 0


def _fmt_wan(value: Any, unit: str = "") -> str:
    """在线人数：接口有时给 "1.5"（单位万），有时给 "9376"（原始人数）。"""
    text = str(value or "").strip()
    if not text or text in ("-", "N/A"):
        return "-"
    if not text.replace(".", "", 1).isdigit():
        return text
    if unit:
        return f"{text} {unit}"
    number = float(text)
    if number >= 10000:
        return f"{number / 10000:.1f} 万"
    return f"{int(number)}" if number.is_integer() else text


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
    intro_length: int = 400,
    req_mode: str = "full",
    sales_limit: int = 3,
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
        if not value or value in ("-", "N/A", ""):
            continue
        if label in ("当前在线", "昨日峰值在线", "小黑盒玩家数"):
            unit = ""
            rich = item.get("hb_rich_text") or {}
            for attr in (rich.get("attrs") or []):
                piece = str(attr.get("text") or "").strip()
                if piece in ("万", "亿"):
                    unit = piece
                    break
            value = _fmt_wan(value, unit)
        card.stats.append(StatCell(label=label, value=value))
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
    card.sales = build_sales(history.get("prices") or [], sales_limit)

    req = requirements or {}
    req_mode = (req_mode or "full").lower()
    keep_keys = ("操作系统", "处理器", "内存", "显卡", "存储空间")
    compact_keys = ("处理器", "内存", "显卡", "存储空间")

    def pick(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
        if req_mode != "compact":
            return rows
        picked = [(k, v) for k, v in rows if k in compact_keys]
        return picked or rows[:4]

    if req_mode != "off":
        card.req_min = pick(list(req.get("minimum") or []))
        card.req_rec = pick(list(req.get("recommended") or []))
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
#card { width:760px; background:$card_bg; color:$text; border-radius:18px; overflow:hidden;
        border:1px solid $border; }
.cover { width:100%; aspect-ratio:16/9; object-fit:cover; display:block; background:$img_bg; }
.body { padding:20px 22px 18px; }
.pricebar { display:flex; align-items:center; justify-content:space-between;
            background:$panel2; border-radius:10px; padding:14px 18px; margin-bottom:16px; }
.price-now { font-size:34px; font-weight:700; color:$price_text; }
.price-old { font-size:15px; color:$dim2; text-decoration:line-through; margin-left:12px; }
.badge { font-size:14px; font-weight:700; color:$white; background:$red; padding:2px 8px;
         border-radius:6px; margin-left:10px; }
.trend { font-size:13px; color:$muted2; }
.title-row { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.title { font-size:32px; font-weight:700; line-height:1.2; }
.title-en { font-size:14px; color:$dim; margin-top:6px; }
.scorebox { background:$orange; border-radius:10px; padding:8px 14px; text-align:center; flex:none; }
.scorebox .s { font-size:26px; font-weight:700; color:$white; line-height:1; }
.scorebox .c { font-size:11px; color:rgba(255,255,255,0.62); margin-top:4px; }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
.chip { font-size:13px; color:$text3; background:$panel2; border:1px solid $chip_border;
        padding:5px 12px; border-radius:7px; }
.chip.plat { color:$chip_plat_text; background:$chip_plat_bg; }
.grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:16px; }
.cell { background:$panel; border-radius:10px; padding:12px 10px; text-align:center; }
.cell .v { font-size:19px; font-weight:700; color:$text; }
.cell .l { font-size:12px; color:$label; margin-top:5px; }
.meta { margin-top:14px; padding-top:12px; border-top:1px solid $border;
         display:flex; flex-wrap:wrap; gap:6px 22px; font-size:12.5px; color:$muted2; }
.meta b { color:$text2; font-weight:600; }
.pricegrid { display:grid; grid-template-columns:1.05fr 1.55fr 1.2fr; gap:10px; margin-top:14px; }
.pcol { background:$panel; border-radius:10px; padding:12px 14px; }
.pcol h3 { font-size:12px; color:$label; font-weight:600; margin-bottom:8px; letter-spacing:1px; }
.pbig { font-size:24px; font-weight:700; color:$green; line-height:1.1; }
.pmeta { font-size:11.5px; color:$label; margin-top:4px; }
.prow { display:flex; justify-content:space-between; font-size:12px; color:$text4; padding:3px 0; }
.prow .dis { color:$red_soft; font-weight:600; }
.req { margin-top:12px; background:$panel; border-radius:10px; padding:11px 16px 12px; }
.req h4 { font-size:12px; color:$label; font-weight:600; margin-bottom:6px; letter-spacing:1px; }
.req-cols { display:grid; grid-template-columns:1fr 1fr; gap:0 26px; }
.req-col h5 { font-size:12.5px; color:$muted; font-weight:700; margin:0 0 5px; }
.req-list { display:block; }
.req-row { display:flex; gap:6px; font-size:12px; line-height:1.55; padding:2px 0; color:$text4; }
.req-k { color:$label2; flex:none; min-width:52px; }
.req-v { flex:1; }
.req .none { color:$faint; font-size:13px; }
.intro { margin-top:12px; font-size:13.5px; color:$text4b; line-height:1.8; }
.footer { display:flex; justify-content:space-between; font-size:12px; color:$faint3;
          margin-top:16px; padding-top:12px; border-top:1px solid $border; }
"""


from string import Template

THEMES = {
    "dark": {
        "card_bg": "#17191e", "panel": "#1d2129", "panel2": "#22262e",
        "border": "#262b34", "chip_border": "#2e3540", "chip_plat_bg": "#2a3340",
        "text": "#e9eef6", "text2": "#dfe7f2", "text3": "#c8d3e2", "text3b": "#c7d2e0",
        "text4": "#b9c5d6", "text4b": "#b3bfd0", "muted": "#aab6c8", "muted2": "#9aa6b8",
        "dim": "#8794a8", "dim2": "#8a95a6", "label": "#7f8da2", "label2": "#7b8798",
        "faint": "#6d7889", "faint2": "#67758a", "faint3": "#5e6a7c",
        "price": "#ffcc66", "price_bg1": "#2a2113", "price_bg2": "#1d1a14",
        "price_border": "#4a3a1c", "green": "#4ade80", "red": "#e5484d",
        "red_soft": "#ff8a8a", "orange": "#f08a24", "img_bg": "#0f1116",
        "white": "#fff", "price_text": "#ffffff", "chip_plat_text": "#ffffff",
    },
    "light": {
        "card_bg": "#ffffff", "panel": "#f4f6f9", "panel2": "#eef1f5",
        "border": "#e4e7ec", "chip_border": "#dde2e8", "chip_plat_bg": "#e8edf4",
        "text": "#15181d", "text2": "#20242b", "text3": "#2f3540", "text3b": "#333a45",
        "text4": "#3b4250", "text4b": "#404856", "muted": "#4b5361", "muted2": "#5b6472",
        "dim": "#666e7c", "dim2": "#6b7381", "label": "#6b7280", "label2": "#707885",
        "faint": "#8a92a0", "faint2": "#8d95a2", "faint3": "#9aa1ad",
        "price": "#b45309", "price_text": "#8a4b08", "chip_plat_text": "#2f3540", "price_bg1": "#fff8e8", "price_bg2": "#fffdf6",
        "price_border": "#f0dcb0", "green": "#15803d", "red": "#d92d20",
        "red_soft": "#ef4444", "orange": "#ea7c1f", "img_bg": "#e9edf2",
        "white": "#fff",
    },
}


def theme_css(template: str, theme: str = "dark") -> str:
    """把 CSS 里的 $token 换成对应主题的颜色。"""
    return Template(template).substitute(**THEMES.get(theme, THEMES["dark"]))


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def render_html(card: CardData, theme: str = "dark") -> str:
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

    meta_bits = []
    if card.release:
        meta_bits.append(f'<span>发布时间 <b>{_esc(card.release)}</b></span>')
    if card.developers:
        meta_bits.append(f'<span>开发商 <b>{_esc(card.developers)}</b></span>')
    if card.publishers:
        meta_bits.append(f'<span>发行商 <b>{_esc(card.publishers)}</b></span>')
    meta_html = f'<div class="meta">{"".join(meta_bits)}</div>' if meta_bits else ""

    def req_column(title: str, rows: list[tuple[str, str]]) -> str:
        if not rows:
            return f'<div class="req-col"><h5>{_esc(title)}</h5><div class="none">无</div></div>'
        body = "".join(
            f'<div class="req-row"><span class="req-k">{_esc(k)}</span>'
            f'<span class="req-v">{_esc(v)}</span></div>' if k else
            f'<div class="req-row"><span class="req-v">{_esc(v)}</span></div>'
            for k, v in rows
        )
        return f'<div class="req-col"><h5>{_esc(title)}</h5><div class="req-list">{body}</div></div>'

    lowest_meta = _esc(card.lowest_date or "")
    if card.lowest_discount:
        lowest_meta += f" · -{card.lowest_discount}%"
    if card.lowest_count:
        lowest_meta += f" · {card.lowest_count} 次"
    gap_text = ""
    try:
        now_price = float(card.price_now)
        low_price = float(card.lowest_price)
        if now_price > low_price > 0:
            gap_text = f"当前高 {((now_price - low_price) / low_price * 100):.0f}%"
    except (TypeError, ValueError):
        pass

    sales_html = "".join(
        f'<div class="prow"><span>{_esc(x.start)[5:]} ~ {_esc(x.end)[5:]}</span>'
        f'<span>¥{_esc(x.price)} <span class="dis">-{x.discount}%</span></span></div>'
        for x in card.sales
    ) or '<div class="prow"><span>近期无促销</span></div>'

    regions_html = "".join(
        f'<div class="prow"><span>{_esc(r["name"])}</span><span>¥{_esc(r["price"])}</span></div>'
        for r in card.regions[:4]
    ) or '<div class="prow"><span>暂无跨区数据</span></div>'

    price_section = (
        '<div class="pricegrid">'
        f'<div class="pcol"><h3>历史最低</h3><div class="pbig">¥{_esc(card.lowest_price or "-")}</div>'
        f'<div class="pmeta">{lowest_meta}</div>'
        + (f'<div class="pmeta">{gap_text}</div>' if gap_text else "")
        + '</div>'
        f'<div class="pcol"><h3>最近促销</h3>{sales_html}</div>'
        f'<div class="pcol"><h3>跨区低价</h3>{regions_html}</div>'
        '</div>'
    )

    if card.req_min or card.req_rec:
        req_html = (
            '<div class="req"><h4>配置要求（Windows）</h4><div class="req-cols">'
            + req_column("最低配置", card.req_min)
            + req_column("推荐配置", card.req_rec)
            + "</div></div>"
        )
    else:
        req_html = '<div class="req"><h4>配置要求</h4><p class="none">暂无数据</p></div>'

    intro_html = f'<div class="intro">{_esc(card.intro)}</div>' if card.intro else ""
    score_html = (
        f'<div class="scorebox"><div class="s">{_esc(card.score)}</div>'
        f'<div class="c">{_esc(card.score_count + " 人评分") if card.score_count else "评分"}</div></div>'
        if card.score else ""
    )
    cover_html = f'<img class="cover" src="{_esc(card.cover)}" />' if card.cover else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{theme_css(CSS, theme)}</style></head>
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
    {price_section}
    {req_html}
    {intro_html}
    {meta_html}
    <div class="footer"><span>数据来源：小黑盒</span><span>{time.strftime('%Y-%m-%d %H:%M')}</span></div>
  </div>
</div></body></html>"""


PRICE_CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { background:transparent; font-family:'WenQuanYi Zen Hei','Noto Sans CJK SC',sans-serif; }
#price-card { width:760px; background:$card_bg; color:$text; border-radius:18px; overflow:hidden;
              border:1px solid $border; padding:22px; }
.head { display:flex; gap:16px; align-items:center; }
.head img { width:150px; height:84px; object-fit:cover; border-radius:10px; background:$img_bg; }
.head .name { font-size:26px; font-weight:700; }
.head .sub { font-size:12.5px; color:$dim; margin-top:5px; }
.big { display:flex; align-items:baseline; gap:14px; margin-top:18px;
       background:linear-gradient(135deg,$price_bg1,$price_bg2); border:1px solid $price_border;
       border-radius:12px; padding:16px 20px; }
.big .now { font-size:44px; font-weight:700; color:$price; }
.big .old { font-size:17px; color:$dim2; text-decoration:line-through; }
.big .off { font-size:15px; font-weight:700; color:$white; background:$red; padding:3px 10px; border-radius:7px; }
.big .tag { font-size:12.5px; color:$muted2; margin-left:auto; }
.section { margin-top:14px; background:$panel; border-radius:12px; padding:14px 16px; }
.section h3 { font-size:13px; color:$label; font-weight:600; margin-bottom:10px; letter-spacing:1px; }
.lowrow { display:flex; align-items:center; gap:16px; }
.lowrow .p { font-size:30px; font-weight:700; color:$green; }
.lowrow .m { font-size:13px; color:$muted2; line-height:1.8; }
.sale { display:flex; justify-content:space-between; font-size:13px; color:$text3b;
        padding:6px 0; border-bottom:1px dashed $border; }
.sale:last-child { border-bottom:none; }
.sale .d { color:$red_soft; font-weight:600; }
.empty { font-size:13px; color:$faint; }
.regions { display:grid; grid-template-columns:1fr 1fr; gap:0 26px; }
.reg { display:flex; justify-content:space-between; font-size:13px; padding:5px 0;
       border-bottom:1px dashed $border; color:$text3b; }
.reg .cc { color:$faint2; font-size:11px; margin-left:6px; }
.footer { display:flex; justify-content:space-between; font-size:12px; color:$faint3;
          margin-top:16px; padding-top:12px; border-top:1px solid $border; }
"""


def render_price_html(card: CardData, theme: str = "dark") -> str:
    """独立的详细价格卡片。"""
    if card.is_free:
        price_html = '<span class="now">免费</span>'
    else:
        price_html = f'<span class="now">¥{_esc(card.price_now or "-")}</span>'
        if card.price_old and card.price_old != card.price_now:
            price_html += f'<span class="old">¥{_esc(card.price_old)}</span>'
        if card.discount > 0:
            price_html += f'<span class="off">-{card.discount}%</span>'

    gap_text = ""
    try:
        now_price = float(card.price_now)
        low_price = float(card.lowest_price)
        if now_price > low_price > 0:
            gap_text = f"当前价比史高高 {((now_price - low_price) / low_price * 100):.0f}%"
        elif now_price <= low_price:
            gap_text = "当前就是史低"
    except (TypeError, ValueError):
        pass

    lowest_meta = []
    if card.lowest_date:
        lowest_meta.append(f"日期 {card.lowest_date}")
    if card.lowest_discount:
        lowest_meta.append(f"折扣 -{card.lowest_discount}%")
    if card.lowest_count:
        lowest_meta.append(f"出现过 {card.lowest_count} 次")
    if gap_text:
        lowest_meta.append(gap_text)

    sales_html = "".join(
        f'<div class="sale"><span>{_esc(x.start)} ~ {_esc(x.end)}（{x.days} 天）</span>'
        f'<span>¥{_esc(x.price)} <span class="d">-{x.discount}%</span></span></div>'
        for x in card.sales
    ) or '<div class="empty">暂无促销记录</div>'

    regions_html = "".join(
        f'<div class="reg"><span>{_esc(r["name"])}<span class="cc">{_esc(r["cc"])}</span></span>'
        f'<span>¥{_esc(r["price"])}</span></div>'
        for r in card.regions
    ) or '<div class="empty">暂无跨区数据</div>'

    cover = f'<img src="{_esc(card.cover)}" />' if card.cover else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{theme_css(PRICE_CSS, theme)}</style></head>
<body><div id="price-card">
  <div class="head">{cover}
    <div><div class="name">{_esc(card.name)}</div>
      <div class="sub">Steam AppID {card.appid}{(" · 小黑盒评分 " + _esc(card.score)) if card.score else ""}</div>
    </div>
  </div>
  <div class="big">{price_html}<span class="tag">历史最低 ¥{_esc(card.lowest_price or "-")}</span></div>
  <div class="section"><h3>历史最低</h3>
    <div class="lowrow"><span class="p">¥{_esc(card.lowest_price or "-")}</span>
      <span class="m">{' · '.join(_esc(x) for x in lowest_meta) or '-'}</span></div>
  </div>
  <div class="section"><h3>促销记录（{len(card.sales)}）</h3>{sales_html}</div>
  <div class="section"><h3>跨区比价（{len(card.regions)}）</h3><div class="regions">{regions_html}</div></div>
  <div class="footer"><span>数据来源：小黑盒</span><span>{time.strftime('%Y-%m-%d %H:%M')}</span></div>
</div></body></html>"""
