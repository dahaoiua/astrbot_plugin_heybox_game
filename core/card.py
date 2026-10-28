"""把小黑盒数据整理成卡片结构，并生成 HTML。"""
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
class CardData:
    appid: int
    name: str
    cover: str = ""
    score: str = ""
    online: str = ""
    follow: str = ""
    tags: str = ""
    release: str = ""
    price_now: str = ""
    price_old: str = ""
    discount: int = 0
    is_free: bool = False
    lowest_price: str = ""
    lowest_date: str = ""
    lowest_discount: int = 0
    lowest_count: int = 0
    sales: list[SaleSegment] = field(default_factory=list)
    regions: list[dict[str, Any]] = field(default_factory=list)


def _fmt_num(value: Any) -> str:
    """把 1750613 / '14万' 之类转成易读的计数。"""
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.isdigit():
        return text
    num = int(text)
    if num >= 100_000_000:
        return f"{num / 100_000_000:.1f} 亿"
    if num >= 10_000:
        return f"{num / 10_000:.1f} 万"
    return str(num)


def _date_from_epoch(value: Any) -> str:
    try:
        ts = int(str(value))
    except (TypeError, ValueError):
        return str(value or "")
    if ts > 10_000_000_000:
        ts //= 1000
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def build_sales(prices: list[dict[str, Any]], limit: int = 3) -> list[SaleSegment]:
    """把历史价格整理成"促销事件"。

    小黑盒的 prices 是按价格变动记录的（不是每日一条）：
    一条 discount>0 的记录 = 一次促销开始，下一条记录（恢复原价）即促销结束。
    """
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
        if index + 1 < len(entries):
            finish = ts(entries[index + 1]) or now
        else:
            finish = now
        days = max(1, round((finish - begin) / 86400))
        events.append(
            SaleSegment(
                start=datetime.fromtimestamp(begin).strftime("%Y-%m-%d"),
                end=datetime.fromtimestamp(finish).strftime("%Y-%m-%d"),
                days=days,
                price=str(entry.get("price") or ""),
                discount=discount,
            )
        )
    return events[-limit:]


def build_card(
    game: dict[str, Any],
    history: dict[str, Any] | None = None,
    regions: list[dict[str, Any]] | None = None,
    max_regions: int = 5,
) -> CardData:
    price = game.get("price") or {}
    try:
        discount = int(price.get("discount") or 0)
    except (TypeError, ValueError):
        discount = 0

    card = CardData(
        appid=int(game.get("steam_appid") or game.get("appid") or 0),
        name=str(game.get("name") or ""),
        cover=str(game.get("head_image_616_353") or game.get("image") or ""),
        score=str(game.get("score") or ""),
        online=_fmt_num(game.get("online_player")),
        follow=_fmt_num(game.get("follow_num")),
        tags=str(game.get("core_tags_str") or game.get("complete_tags_str") or ""),
        release=str(game.get("release_date_desc") or game.get("release_date") or ""),
        price_now=str(price.get("current") if price.get("current") is not None else ""),
        price_old=str(price.get("initial") if price.get("initial") is not None else ""),
        discount=discount,
        is_free=bool(game.get("is_free")),
    )

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
    elif isinstance(price, dict):
        card.lowest_price = str(price.get("lowest_price_raw") or "")
    if isinstance(lowest_v2, dict):
        try:
            card.lowest_count = int(lowest_v2.get("count") or 0)
        except (TypeError, ValueError):
            card.lowest_count = 0

    card.sales = build_sales(history.get("prices") or [])

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
            "discount": int(region.get("discount") or 0),
        })
    items.sort(key=lambda x: float(x["price"]))
    card.regions = items[:max_regions]
    return card


CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { background:transparent; font-family:'WenQuanYi Zen Hei','Noto Sans CJK SC',sans-serif; }
#card {
  width: 760px; padding: 26px; border-radius: 22px; color:#e9eef6;
  background: linear-gradient(160deg,#23272f 0%,#171a20 55%,#14161b 100%);
  border: 1px solid #2e343f;
}
.cover { width:100%; aspect-ratio:616/353; object-fit:cover; border-radius:14px; display:block;
         background:#0f1116; border:1px solid #2b313b; }
.head { display:flex; align-items:flex-end; justify-content:space-between; margin-top:18px; gap:12px; }
.title { font-size:30px; font-weight:700; letter-spacing:.5px; }
.appid { font-size:13px; color:#8c98ab; margin-top:6px; }
.score { font-size:34px; font-weight:700; color:#ffd166; line-height:1; }
.score small { font-size:12px; color:#8c98ab; font-weight:400; margin-left:4px; }
.stats { display:flex; gap:18px; margin-top:14px; font-size:14px; color:#aab6c8; }
.stats b { color:#e9eef6; font-weight:600; }
.pricebox { margin-top:18px; padding:18px 20px; border-radius:16px;
            background:linear-gradient(135deg,#2a2113,#1d1a14); border:1px solid #4a3a1c;
            display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
.price-now { font-size:42px; font-weight:700; color:#ffcc66; }
.price-old { font-size:17px; color:#8c98ab; text-decoration:line-through; }
.badge { font-size:15px; font-weight:700; color:#fff; background:#e5484d;
         padding:3px 10px; border-radius:8px; }
.free { color:#4ade80; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:16px; }
.panel { background:#1c2027; border:1px solid #2b313b; border-radius:14px; padding:16px 18px; }
.panel h3 { font-size:14px; color:#8c98ab; font-weight:600; margin-bottom:12px; letter-spacing:1px; }
.lowest-price { font-size:26px; font-weight:700; color:#4ade80; }
.lowest-meta { font-size:13px; color:#8c98ab; margin-top:6px; }
.sale { display:flex; justify-content:space-between; font-size:13.5px; color:#c7d2e0; padding:5px 0;
        border-bottom:1px dashed #2b313b; }
.sale:last-child { border-bottom:none; }
.sale .dis { color:#ff8a8a; font-weight:600; }
.region { display:flex; justify-content:space-between; font-size:13.5px; padding:5px 0; color:#c7d2e0; }
.region .cc { color:#6f7d92; margin-left:6px; font-size:12px; }
.tags { margin-top:16px; font-size:13px; color:#9fb0c7; }
.footer { margin-top:18px; padding-top:14px; border-top:1px solid #262c36;
          display:flex; justify-content:space-between; font-size:12px; color:#67758a; }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def render_html(card: CardData) -> str:
    if card.is_free:
        price_block = '<div class="price-now free">免费</div>'
    else:
        price_block = f'<div class="price-now">¥{_esc(card.price_now or "-")}</div>'
        if card.price_old and card.price_old != card.price_now:
            price_block += f'<div class="price-old">¥{_esc(card.price_old)}</div>'
        if card.discount > 0:
            price_block += f'<div class="badge">-{card.discount}%</div>'

    gap_text = ""
    try:
        now_price = float(card.price_now)
        low_price = float(card.lowest_price)
        if now_price > low_price > 0:
            gap_text = f' · 当前高 {((now_price - low_price) / low_price * 100):.0f}%'
    except (TypeError, ValueError):
        pass

    lowest_block = (
        f'<div class="lowest-price">¥{_esc(card.lowest_price or "-")}</div>'
        f'<div class="lowest-meta">{_esc(card.lowest_date or "")}'
        + (f' · -{card.lowest_discount}%' if card.lowest_discount else "")
        + (f' · 出现 {card.lowest_count} 次' if card.lowest_count else "")
        + gap_text
        + "</div>"
    )

    sales_html = "".join(
        f'<div class="sale"><span>{_esc(s.start)} ~ {_esc(s.end)}</span>'
        f'<span>¥{_esc(s.price)} <span class="dis">-{s.discount}%</span></span></div>'
        for s in card.sales
    ) or '<div class="sale"><span>近期无促销</span></div>'

    regions_html = "".join(
        f'<div class="region"><span>{_esc(r["name"])}<span class="cc">{_esc(r["cc"])}</span></span>'
        f'<span>¥{_esc(r["price"])}</span></div>'
        for r in card.regions
    ) or '<div class="region"><span>暂无跨区数据</span></div>'

    stats = []
    if card.online:
        stats.append(f'<div><b>{_esc(card.online)}</b> 在线</div>')
    if card.follow:
        stats.append(f'<div><b>{_esc(card.follow)}</b> 关注</div>')
    if card.release:
        stats.append(f'<div>{_esc(card.release)}</div>')

    cover = f'<img class="cover" src="{_esc(card.cover)}" />' if card.cover else ""
    tags = f'<div class="tags">{_esc(card.tags)}</div>' if card.tags else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body><div id="card">
  {cover}
  <div class="head">
    <div>
      <div class="title">{_esc(card.name)}</div>
      <div class="appid">Steam AppID {card.appid}</div>
    </div>
    <div class="score">{_esc(card.score or "-")}<small>/10</small></div>
  </div>
  <div class="stats">{''.join(stats)}</div>
  <div class="pricebox">{price_block}</div>
  <div class="grid">
    <div class="panel"><h3>历史最低</h3>{lowest_block}</div>
    <div class="panel"><h3>最近促销</h3>{sales_html}</div>
  </div>
  <div class="panel" style="margin-top:14px"><h3>跨区低价（前 {len(card.regions)}）</h3>{regions_html}</div>
  {tags}
  <div class="footer"><span>数据来源：小黑盒</span><span>{time.strftime('%Y-%m-%d %H:%M')}</span></div>
</div></body></html>"""
