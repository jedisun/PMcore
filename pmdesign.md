# Polymarket 后台应用设计 v2

## 1. 目标与范围

构建一个基于 Polymarket 的后台应用，第一阶段以 CLI 运行，后续平滑扩展为服务化系统。

系统分为两条主线：

1. 只读数据能力
   - 市场发现
   - order book / price / trades 数据抓取
   - WebSocket 实时订阅
   - 本地缓存与数据库落库

2. 交易执行能力
   - CLOB 认证与账户初始化
   - 下单、撤单、查单、查成交
   - heartbeat 与 open order 生命周期维护
   - 基础风控与执行保护

目标不是做一组脚本，而是搭建一个可复用的后台内核：

- 第一阶段：CLI
- 第二阶段：服务化 API
- 第三阶段：策略、告警、审计与运营后台

---

## 2. 官方约束整理

### 2.1 API 分层

- `Gamma API`
  负责市场发现、事件、标签、市场元数据
- `Data API`
  负责公共和用户相关查询，如 activity、positions、历史数据
- `CLOB API`
  负责订单簿、下单、撤单、用户订单、用户成交、交易 WebSocket

结论：

- 市场发现与资产建模基于 `Gamma`
- 交易、盘口、用户订单状态基于 `CLOB`
- 账户状态、审计与分析可结合 `Data API`

### 2.2 交易认证模型

Polymarket 交易不能被抽象成“拿一把私钥直接发 REST 请求”。

交易路径至少涉及：

- L1 身份
- L2 API credentials
- `signature_type`
- `funder`

并且不同钱包模式会影响签名和账户配置：

- EOA
- Polymarket Proxy
- Gnosis Safe

结论：

- “账户与交易身份”必须成为一等模型
- 不能把所有交易凭证都压成一组全局环境变量

### 2.3 订单与执行约束

交易不是只有“限价买卖”这一个维度，还要覆盖：

- `GTC`
- `GTD`
- `FOK`
- `FAK`
- `postOnly`
- batch create / cancel
- partial fill
- open order heartbeat

结论：

- 订单表与订单状态机必须从第一天就支持这些字段
- heartbeat 不能只是单独一个 cron job

### 2.4 Geoblock 与运行边界

Polymarket 存在地理限制检查。检查对象不是抽象账户，而是请求出口。

结论：

- 单用户 bot：检查部署机出口 IP
- 多用户系统：必须明确用户侧访问与服务端代执行的边界

### 2.5 WebSocket 现实约束

实时链路不能只写“自动重连”。

必须显式设计：

- REST 初始快照
- WebSocket 增量更新
- 断线重拉快照
- 用户频道和市场频道分离
- schema 变更兼容

---

## 3. 设计原则

1. CLI 只是入口，不承载业务逻辑
2. 所有外部 API 交互集中在 client 层
3. 交易身份、市场资产、订单生命周期必须显式建模
4. 所有关键状态可审计、可恢复、可重放
5. 只读链路与交易链路隔离，防止研究功能污染交易主路径

---

## 4. 技术选型

### 4.1 语言

推荐：Python 3.11+

原因：

- 官方 Python CLOB client 可直接复用
- 异步 IO、CLI、数据处理生态成熟
- 适合先做后台内核，再逐步服务化

### 4.2 技术栈

- Python 3.11+
- 官方 Python CLOB client
- `httpx`
- `websockets`
- `Typer`
- `Pydantic v2`
- `pydantic-settings`
- `SQLAlchemy 2.x`
- `Alembic`
- `pytest`
- `pytest-asyncio`

数据库策略：

- 主路径：PostgreSQL
- SQLite 仅作为本地轻量实验或临时测试替身，不作为正式演进目标

---

## 5. 总体架构

```text
┌──────────────────────────────┐
│            CLI 层            │
│ markets / book / order ...  │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│         应用服务层            │
│ MarketService                │
│ BookService                  │
│ AccountService               │
│ OrderService                 │
│ PositionService              │
│ PreTradeChecks               │
│ ExecutionGuard               │
│ StreamService                │
│ HealthService                │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│         基础设施层            │
│ GammaClient                  │
│ DataClient                   │
│ ClobClient                   │
│ WsMarketClient               │
│ WsUserClient                 │
│ Repository / DB              │
│ Config / Logger              │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│         外部系统              │
│ Gamma API                    │
│ Data API                     │
│ CLOB API                     │
│ Market WS / User WS          │
└──────────────────────────────┘
```

---

## 6. 核心域模型

### 6.1 交易账户模型

新增 `trading_accounts`，用于表达真实交易身份。

建议字段：

- `account_id`
- `name`
- `wallet_type`
- `signature_type`
- `signer_address`
- `funder_address`
- `api_key`
- `api_secret`
- `api_passphrase`
- `trading_enabled`
- `geo_status`
- `created_at`
- `updated_at`

说明：

- `wallet_type` 区分 EOA / Proxy / Safe
- `signature_type` 决定下单签名路径
- `funder_address` 不能只作为配置备注，必须入库并进入执行上下文

### 6.2 市场与资产模型

不要再把市场写死成 `yes_token_id / no_token_id`。

推荐三层：

- `events`
- `markets`
- `market_outcomes`

其中 `market_outcomes` 表达：

- `token_id`
- `outcome_index`
- `outcome_label`
- `is_tradable`
- `neg_risk`

结论：

- 二元市场只是一个特例
- 数据模型必须允许未来出现多 outcome 或特殊市场形态

### 6.3 订单生命周期模型

订单不是一次请求，而是一条状态流。

至少需要表达：

- create requested
- accepted
- open
- partially filled
- filled
- cancel requested
- cancelled
- expired
- rejected

因此必须新增 `order_events`，保存原始状态变化，而不是只覆盖更新 `orders.status`。

---

## 7. 功能模块拆解

### 7.1 MarketService

职责：

- 同步事件和市场
- 维护 `event -> market -> outcome token` 映射
- 提供市场搜索、筛选、状态查询

### 7.2 BookService

职责：

- 拉取 order book 快照
- 聚合 best bid / ask / mid / spread
- 保存 book snapshots
- 支持短周期价格序列聚合

### 7.3 AccountService

职责：

- 账户初始化
- 管理交易身份
- 加载和刷新 API credentials
- 查询余额、allowance、geo 状态

### 7.4 OrderService

职责：

- 创建订单
- 撤单
- 查询订单与成交
- 维护本地订单主记录

### 7.5 PreTradeChecks

职责：

- geoblock 检查
- tick size / min order size 校验
- allowance / balance / inventory 检查
- 最大价格偏离校验
- 最大下单额与风险限额检查

### 7.6 ExecutionGuard

职责：

- 幂等保护
- 重试策略
- 部分成交处理
- open order heartbeat
- 撤单恢复和失败熔断

### 7.7 StreamService

职责：

- 管理市场 WS
- 管理用户 WS
- 断线重连
- 快照与增量对账
- 事件 schema 版本兼容

### 7.8 PositionService

职责：

- 同步 positions / trades / activity
- 计算成本和基础 PnL
- 做订单和成交对账

### 7.9 HealthService

职责：

- API 连通性检查
- DB 健康检查
- Market WS 健康检查
- User WS 健康检查
- heartbeat 状态检查

---

## 8. 数据库设计

### 8.1 events

- `id`
- `event_id`
- `title`
- `slug`
- `category`
- `active`
- `closed`
- `raw_json`
- `created_at`
- `updated_at`

### 8.2 markets

- `id`
- `market_id`
- `event_id`
- `condition_id`
- `title`
- `slug`
- `active`
- `closed`
- `archived`
- `liquidity`
- `volume`
- `tick_size`
- `min_order_size`
- `enable_order_book`
- `raw_json`
- `created_at`
- `updated_at`

### 8.3 market_outcomes

- `id`
- `market_id`
- `token_id`
- `outcome_index`
- `outcome_label`
- `neg_risk`
- `is_tradable`
- `raw_json`
- `created_at`
- `updated_at`

### 8.4 trading_accounts

- `id`
- `account_id`
- `name`
- `wallet_type`
- `signature_type`
- `signer_address`
- `funder_address`
- `trading_enabled`
- `geo_status`
- `created_at`
- `updated_at`

### 8.5 balances

- `id`
- `account_id`
- `asset_type`
- `asset_id`
- `available`
- `locked`
- `snapshot_time`

### 8.6 allowances

- `id`
- `account_id`
- `asset_id`
- `spender`
- `allowance`
- `snapshot_time`

### 8.7 order_books

- `id`
- `market_id`
- `token_id`
- `best_bid`
- `best_ask`
- `mid_price`
- `spread`
- `bids_json`
- `asks_json`
- `captured_at`

### 8.8 price_history

- `id`
- `token_id`
- `interval`
- `timestamp`
- `price`
- `volume`

### 8.9 orders

- `id`
- `account_id`
- `client_order_id`
- `exchange_order_id`
- `token_id`
- `side`
- `price`
- `size`
- `filled_size`
- `remaining_size`
- `order_type`
- `time_in_force`
- `post_only`
- `expires_at`
- `status`
- `cancel_reason`
- `raw_request`
- `raw_response`
- `created_at`
- `updated_at`

### 8.10 order_events

- `id`
- `order_id`
- `event_type`
- `payload_json`
- `event_time`

### 8.11 trades

- `id`
- `account_id`
- `trade_id`
- `order_id`
- `token_id`
- `side`
- `price`
- `size`
- `fee`
- `trade_time`
- `raw_json`

### 8.12 positions

- `id`
- `account_id`
- `token_id`
- `size`
- `avg_cost`
- `mark_price`
- `unrealized_pnl`
- `realized_pnl`
- `snapshot_time`

---

## 9. WebSocket 恢复与对账策略

这是 v2 新增的核心章节。

### 9.1 市场数据链路

标准流程：

1. REST 拉取初始快照
2. 建立市场 WebSocket
3. 接收增量事件并更新内存缓存
4. 周期性与 REST 快照对账
5. 若断线或校验失败，则丢弃本地快照并重新初始化

### 9.2 用户数据链路

用户频道与市场频道必须分离。

原因：

- 生命周期不同
- 失败影响不同
- 用户状态需要更高可靠性

### 9.3 schema 兼容策略

为所有 WebSocket 消息做版本化适配：

- 原始 payload 落日志
- parser 层统一转成内部事件模型
- 解析失败要告警，不可静默吞掉

---

## 10. 交易前检查与执行保护

### 10.1 PreTradeChecks

在真正调用下单接口前，至少检查：

- geoblock 是否通过
- 账户是否启用交易
- `signature_type` 和 `funder` 是否完整
- tick size 是否匹配
- min order size 是否满足
- 余额是否足够
- allowance 是否足够
- 价格偏离是否超限
- 市场是否 active / tradable

### 10.2 ExecutionGuard

执行层负责：

- 幂等键
- 请求重试策略
- 部分成交后的状态推进
- cancel 与 replace 的一致性
- open orders 的 heartbeat
- 失败阈值熔断

说明：

- heartbeat 不是普通 job，而是 open order session 的组成部分
- 没有 open orders 时，不必维持 heartbeat

---

## 11. CLI 设计

```bash
pm markets sync
pm markets list
pm markets show --market <market_id>
pm outcomes list --market <market_id>

pm book show --token <token_id>
pm book watch --token <token_id>
pm price history --token <token_id> --interval 1h

pm accounts list
pm account show --account <account_id>
pm account balances --account <account_id>
pm account allowances --account <account_id>

pm order buy --account <account_id> --token <token_id> --price 0.45 --size 20 --tif gtc
pm order sell --account <account_id> --token <token_id> --price 0.62 --size 10 --post-only
pm order cancel --account <account_id> --order-id <id>
pm orders open --account <account_id>
pm orders events --order-id <id>

pm trades list --account <account_id>
pm positions list --account <account_id>

pm heartbeat status --account <account_id>
pm health check
```

CLI 原则：

- 所有命令支持 `--json`
- 所有交易命令显式要求 `--account`
- 默认只读模式运行

---

## 12. 项目目录结构建议

```text
polymarket-app/
├─ pyproject.toml
├─ README.md
├─ .env.example
├─ alembic.ini
├─ migrations/
├─ src/
│  └─ polymarket_app/
│     ├─ __init__.py
│     ├─ main.py
│     ├─ config/
│     │  ├─ settings.py
│     │  └─ logging.py
│     ├─ clients/
│     │  ├─ gamma_client.py
│     │  ├─ data_client.py
│     │  ├─ clob_client.py
│     │  ├─ ws_market_client.py
│     │  └─ ws_user_client.py
│     ├─ domain/
│     │  ├─ accounts.py
│     │  ├─ markets.py
│     │  ├─ outcomes.py
│     │  ├─ orders.py
│     │  └─ positions.py
│     ├─ repositories/
│     │  ├─ event_repo.py
│     │  ├─ market_repo.py
│     │  ├─ outcome_repo.py
│     │  ├─ account_repo.py
│     │  ├─ order_repo.py
│     │  └─ trade_repo.py
│     ├─ services/
│     │  ├─ market_service.py
│     │  ├─ book_service.py
│     │  ├─ account_service.py
│     │  ├─ order_service.py
│     │  ├─ position_service.py
│     │  ├─ pretrade_checks.py
│     │  ├─ execution_guard.py
│     │  ├─ stream_service.py
│     │  └─ health_service.py
│     ├─ tasks/
│     │  ├─ scheduler.py
│     │  ├─ market_sync.py
│     │  ├─ reconciliation.py
│     │  └─ healthcheck.py
│     ├─ cli/
│     │  ├─ app.py
│     │  ├─ markets.py
│     │  ├─ accounts.py
│     │  ├─ book.py
│     │  ├─ orders.py
│     │  ├─ trades.py
│     │  ├─ positions.py
│     │  └─ health.py
│     └─ utils/
│        ├─ ids.py
│        ├─ retry.py
│        ├─ decimal.py
│        └─ time.py
└─ tests/
```

---

## 13. 配置设计

`.env.example`

```env
APP_ENV=dev
APP_LOG_LEVEL=INFO

DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/pmcore

POLY_PRIVATE_KEY=
POLY_FUNDER=
POLY_SIGNATURE_TYPE=
POLY_API_KEY=
POLY_API_SECRET=
POLY_API_PASSPHRASE=

PM_ENABLE_TRADING=false
PM_ENABLE_WEBSOCKET=true

PM_MAX_ORDER_NOTIONAL=100
PM_MAX_MARKET_EXPOSURE=500
PM_MAX_TOTAL_EXPOSURE=2000
PM_MAX_PRICE_DEVIATION_BPS=100
```

说明：

- 配置只用于默认 profile
- 真正多账户运行时，交易身份以数据库记录为准
- 默认数据库示例使用 PostgreSQL
- 若本地临时切换 SQLite，仅用于开发便利，不保证覆盖完整交易链路

---

## 14. 里程碑重排

### M0：模型定稿

目标：

- 先定稿账户认证模型
- 定稿事件/市场/outcome 数据模型
- 定稿订单状态机和 heartbeat 语义

### M1：只读市场与 book

范围：

- 市场同步
- 市场搜索
- order book 查询
- price history 查询
- 市场 WebSocket
- 本地落库

### M2：交易前检查与账户状态

范围：

- 账户初始化
- balances / allowances 同步
- geoblock 检查
- PreTradeChecks

### M3：交易执行版

范围：

- 下单 / 撤单
- 用户订单状态同步
- order events
- heartbeat
- 执行保护

### M4：持仓、PnL、服务化

范围：

- positions / trades / activity
- PnL
- 审计与对账
- FastAPI 服务化

---

## 15. 开发优先级

第一优先级：

1. 模型定稿
2. 项目骨架
3. MarketService
4. BookService
5. CLI 入口

第二优先级：

6. 市场 WebSocket
7. 数据库落库
8. HealthService

第三优先级：

9. AccountService
10. PreTradeChecks
11. balances / allowances

第四优先级：

12. OrderService
13. ExecutionGuard
14. heartbeat
15. 用户 WebSocket

第五优先级：

16. positions / trades / PnL
17. 对账
18. FastAPI

### 15.1 实施单元拆分

为保证每个阶段都可测试、可回归，开发按以下 15 个小单元推进：

1. `settings`
2. `logging`
3. domain models
4. DB models + migrations
5. `GammaClient`
6. `MarketService.sync_markets`
7. `BookService.get_book`
8. CLI `markets sync`
9. CLI `book show`
10. `AccountService`
11. `PreTradeChecks`
12. `OrderService.place_order`
13. `ExecutionGuard`
14. `WsMarketClient`
15. `WsUserClient`

说明：

- 这 15 个单元是对里程碑和优先级的进一步细化，不改变 `M0 -> M4` 的总体顺序
- 前 1-9 项属于“只读与基础设施优先”
- 10-15 项进入交易与实时状态链路

### 15.2 并行策略

允许并行的部分：

- `GammaClient` 与 DB schema
- `MarketService.sync_markets` 与 `BookService.get_book`
- CLI `markets sync` 与 CLI `book show`
- `AccountService` 与 balances / allowances 同步
- `WsMarketClient` 与 REST book 读取
- `OrderService.place_order` 与 `WsUserClient`

不建议并行的部分：

- 账户认证模型与交易执行模型
- 订单状态机与用户事件映射
- `ExecutionGuard` 与 heartbeat 语义

原因：

- 这些部分耦合较强，过早并行会造成接口反复修改

### 15.3 测试策略

每个小单元必须满足：

- 至少 1 个单元测试文件
- 至少 1 组正常路径用例
- 至少 1 组错误或边界用例
- 若涉及 HTTP / WebSocket，必须提供 mock 或 fake 测试

建议测试目录：

```text
tests/
├─ unit/
├─ integration/
├─ cli/
└─ fixtures/
```

建议测试范围：

- `settings` / `logging`：环境变量、默认值、非法值、输出格式
- domain / DB：字段约束、枚举、迁移、upsert
- clients：请求构造、响应解析、异常映射、限流/重试
- services：同步逻辑、过滤、聚合、审计落库
- pre-trade：tick size、min order size、allowance、余额、geoblock
- order execution：幂等、部分成交、取消、失败恢复
- websocket：快照、增量、断线重连、坏消息处理
- CLI：参数解析、输出格式、错误码、`--json`

---

## 16. 下一步建议

v2 设计完成后，最合理的下一步不是直接开始交易代码，而是：

1. 先按 v2 创建项目骨架
2. 先实现 `events / markets / market_outcomes`
3. 再实现只读 market/book CLI
4. 在此基础上再接入账户与交易能力

如果继续推进，下一步最适合做的是：

- 输出项目骨架
- 创建配置系统
- 建立核心 domain models
- 搭建 `markets sync` 与 `book show` 两条只读链路
