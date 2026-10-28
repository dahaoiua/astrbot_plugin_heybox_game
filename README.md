# astrbot_plugin_heybox_game

小黑盒游戏卡片插件 —— 输入**游戏名 / appid / 小黑盒或 Steam 游戏链接**，抓取小黑盒数据，绘制成一张仿小黑盒游戏页的卡片图。

![预览](docs/preview.jpg)

## 功能

| 信息 | 来源 | 说明 |
| --- | --- | --- |
| 封面 | 详情接口 | 16:9 大图 |
| 中文名 / 英文名 | 详情接口 | 双标题 |
| 价格 / 原价 / 折扣 | 详情接口 | 当前价、原价、折扣百分比 |
| 评分 / 评分人数 | 详情接口 | 橙色评分徽章 |
| 平台 | 详情接口 | Steam / Epic / Xbox / PSN |
| 标签 | 详情接口 | 心愿单热门、动作、冒险、类魂 等 |
| 数据格 | 详情接口 `user_num` | 当前在线、史低价格、好评率、昨日峰值、销量排行、玩家数、平均游戏时间（接口返回空值的格子自动隐藏） |
| 发布时间 / 开发商 / 发行商 | 详情接口 `menu_v2` | 与小黑盒页面一致 |
| 配置要求 | 硬件配置接口 | 最低配置 / 推荐配置，两列竖排（Windows） |
| 游戏简介 | 详情接口 | 可配置截断长度 |
| 历史最低价 | 历史价格接口 | 价格、日期、折扣、出现次数 |
| 促销记录 | 历史价格接口 | 最近 3 次促销的时间区间与折扣 |
| 跨区价格 | 跨区接口 | 折算人民币后的低价区服排行 |

## 输入解析

只处理游戏相关输入，其它链接一律不响应：

```
/小黑盒 赛博朋克2077
/小黑盒 1091500
/小黑盒 https://www.xiaoheihe.cn/app/topic/game/pc/1245620
/小黑盒 https://store.steampowered.com/app/730/
```

别名：`/xhh`、`/游戏价格`、`/steamprice`、`/查价`

## 扫码登录

```
/小黑盒登录     # 管理员可触发，用小黑盒 APP 扫码
/小黑盒状态     # 查看当前 cookie 状态
```

登录成功后凭证保存在 `data/plugin_data/astrbot_plugin_heybox_game/credentials.json`，后续自动使用。

## 安装

1. 把仓库目录放到 AstrBot 的 `data/plugins/astrbot_plugin_heybox_game/`
2. 重启 AstrBot

依赖全部由 AstrBot 核心提供：`aiohttp`、`Pillow`、`qrcode`、`playwright`。
若提示找不到浏览器：

```bash
python -m playwright install chromium
```

## 配置项

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `cookies` | text | 空 | `user_pkey=xxx; heybox_id=123`，留空则用扫码登录保存的凭证 |
| `show_requirements` | bool | true | 显示配置要求（来自小黑盒硬件配置接口） |
| `steam_requirements` | bool | false | 小黑盒拿不到时是否用 Steam 兜底（需代理，可选） |
| `requirements_timeout` | float | 4.0 | Steam 兜底请求超时 |
| `proxy` | string | 空 | 仅在 Steam 兜底时使用，如 `http://127.0.0.1:7890` |
| `days` | int | 720 | 历史价格回溯天数 |
| `max_regions` | int | 5 | 跨区比价显示数量 |
| `max_tags` | int | 8 | 标签最多显示几个 |
| `intro_length` | int | 120 | 简介截断长度，0 = 不显示 |
| `timeout` | int | 20 | 小黑盒请求超时 |
| `render_width` | int | 760 | 卡片宽度 |
| `render_scale` | float | 2.0 | 渲染倍率 |
| `cache_keep_seconds` | int | 3600 | 生成图片保留时长 |
| `admin_only_login` | bool | true | 仅管理员可扫码登录 |

### cookie 优先级

```
配置里的 cookies  >  credentials.json（扫码登录保存）  >  无（仅公开数据）
```

## 数据来源

| 接口 | 用途 |
| --- | --- |
| `/game/search/` | 名称搜索、appid 定位 |
| `/game/get_game_detail/` | 详情（需签名 `_time` + `nonce` + `hkey`） |
| `/game/get_game_prices/history/v2` | 历史价格与史低（`cc` 必须小写 `cn`） |
| `/game/get_game_global_prices/` | 跨区价格 |
| `/pc/get_game_hardware_performance_board/` | 配置要求（最低 / 推荐） |

签名算法与扫码登录实现在 `core/login.py`，来源见文件头注释。

## 常见问题

**Q：提示"未安装 playwright"**
A：在 AstrBot 使用的 Python 环境里执行 `python -m playwright install chromium`。

**Q：cookie 失效**
A：重新 `/小黑盒登录` 扫码，或在配置里填新的 `cookies`。

**Q：搜不到某个游戏**
A：小黑盒搜索按中文名匹配，可直接用 appid 或 Steam 链接。

**Q：在线趋势没有数值**
A：小黑盒详情接口对该字段返回 `-`（需要客户端上下文才计算），插件会自动隐藏空数据格。

**Q：配置要求为空**
A：部分小游戏在硬件配置接口里没有收录，此时会显示"暂无数据"。

## 免责声明

数据来自小黑盒公开接口，仅供个人查询使用。接口可能随时变更，若失效请提 issue。
