# 第一批实现详细设计

## 1. 范围

第一批实现只覆盖基础骨架与开发底座，不进入真实交易逻辑。

交付范围：

1. 项目骨架
2. `pyproject.toml`
3. `.env.example`
4. `settings` 模块
5. `logging` 模块
6. 最小 CLI 入口
7. 对应测试

目标：

- 项目可安装、可运行、可测试
- 配置读取与校验具备稳定边界
- 日志初始化统一，后续模块直接复用
- 为第二批只读 client / service 开发提供基础设施

---

## 2. 目录结构

第一批完成后，目录至少应为：

```text
PMcore/
├─ pyproject.toml
├─ .env.example
├─ README.md
├─ pmdesign.md
├─ phase1-detailed-design.md
├─ src/
│  └─ polymarket_app/
│     ├─ __init__.py
│     ├─ main.py
│     └─ config/
│        ├─ __init__.py
│        ├─ settings.py
│        └─ logging.py
└─ tests/
   ├─ unit/
   │  ├─ test_settings.py
   │  └─ test_logging.py
   └─ cli/
      └─ test_cli_bootstrap.py
```

---

## 3. `pyproject.toml` 设计

### 3.1 项目元数据

- `name = "pmcore"`
- `version = "0.1.0"`
- `requires-python = ">=3.11"`
- 使用 `src/` layout

### 3.2 运行依赖

- `typer`
- `httpx`
- `pydantic`
- `pydantic-settings`
- `structlog`
- `sqlalchemy`
- `psycopg[binary]`

说明：

- 第一批引入数据库基础依赖，但只做连接与配置层，不实现完整 repository
- 后续在第二批、第三批按模块加入，避免骨架期依赖膨胀

### 3.3 开发依赖

- `pytest`
- `pytest-asyncio`
- `pytest-cov`
- `ruff`
- `mypy`

### 3.4 CLI 入口

暴露命令：

- `pm = polymarket_app.main:app`

### 3.5 工具配置

需要在 `pyproject.toml` 中加入：

- `pytest` 配置
- `ruff` 配置
- `mypy` 配置

建议：

- `pytest` 默认扫描 `tests/`
- `pytest-asyncio` 使用 `auto`
- `ruff` 先控制在基础规则集
- `mypy` 先检查 `src/`

---

## 4. `.env.example` 设计

第一批只放基础运行参数，不要求所有交易参数都可立即使用。

建议字段：

```env
APP_ENV=dev
APP_LOG_LEVEL=INFO
APP_LOG_JSON=false
APP_LOG_HTTP=false
APP_LOG_WS=false

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

- 第一批实现时，交易字段允许为空
- 但 `settings` 模块必须支持“交易模式下进行完整性校验”
- PostgreSQL 是默认主路径
- SQLite 仅作为本地临时实验配置，不作为正式开发目标

---

## 5. `settings` 模块设计

### 5.1 目标

`settings` 只负责：

- 从环境变量读取配置
- 做类型转换
- 做基础校验
- 提供统一配置对象

不负责：

- 业务逻辑
- API 调用
- 日志初始化

### 5.2 配置对象拆分

建议拆成四组：

#### `AppSettings`

- `app_env`
- `log_level`
- `log_json`
- `log_http`
- `log_ws`

#### `DatabaseSettings`

- `database_url`
- `database_enabled`

#### `PolymarketSettings`

- `private_key`
- `funder`
- `signature_type`
- `api_key`
- `api_secret`
- `api_passphrase`
- `enable_trading`
- `enable_websocket`

#### `RiskSettings`

- `max_order_notional`
- `max_market_exposure`
- `max_total_exposure`
- `max_price_deviation_bps`

### 5.3 顶层聚合对象

提供一个聚合型 `Settings`：

- `app`
- `database`
- `polymarket`
- `risk`

建议接口：

- `Settings.load()`
- `settings.validate_for_readonly()`
- `settings.validate_for_trading()`

### 5.4 校验规则

只读模式：

- 只要求基础配置合法
- 不强制要求交易凭证

交易模式：

- `enable_trading=true` 时，以下字段必须完整：
  - `private_key`
  - `funder`
  - `signature_type`
  - `api_key`
  - `api_secret`
  - `api_passphrase`

附加规则：

- `log_level` 必须是合法级别
- 金额和风险参数必须为非负
- `database_url` 不可为空
- 若 `database_enabled=true`，则 `database_url` 必须是合法 DSN

### 5.5 测试用例

`tests/unit/test_settings.py`

至少覆盖：

1. 默认值加载
2. 环境变量覆盖
3. 非法 `log_level`
4. 非法数值配置
5. 只读模式允许交易字段为空
6. 交易模式下缺凭证时报错

---

## 6. `logging` 模块设计

### 6.1 目标

统一日志初始化入口，避免后续模块各自配置 logging。

### 6.2 设计原则

- 默认 `INFO`
- 支持 JSON / 人类可读两种格式
- 支持 HTTP 与 WS 细粒度日志开关
- 保证 CLI 和测试环境都能稳定工作

### 6.3 接口设计

建议提供：

- `configure_logging(settings: AppSettings) -> None`
- `get_logger(name: str)`

### 6.4 输出字段

统一日志字段建议包括：

- `timestamp`
- `level`
- `event`
- `logger`
- `app_env`

后续业务日志可追加：

- `account_id`
- `market_id`
- `token_id`
- `order_id`

### 6.5 日志级别

- `DEBUG`
  本地开发、请求调试
- `INFO`
  默认运行级别
- `WARNING`
  可恢复异常
- `ERROR`
  失败或需要人工关注的异常
- `CRITICAL`
  系统不可用、交易必须停止

### 6.6 开关设计

由 `AppSettings` 控制：

- `log_json`
- `log_http`
- `log_ws`

含义：

- `log_json=true` 输出 JSON 结构化日志
- `log_http=true` 允许记录 HTTP 请求/响应摘要
- `log_ws=true` 允许记录 WebSocket 收发摘要

注意：

- 第一批只实现开关和基础 logger，不实现完整 HTTP/WS 中间件

### 6.7 测试用例

`tests/unit/test_logging.py`

至少覆盖：

1. `configure_logging` 可重复调用
2. `INFO` / `DEBUG` 级别生效
3. JSON 与非 JSON 模式切换
4. logger 可正常输出基础字段

---

## 7. CLI 入口设计

### 7.1 第一批目标

CLI 先只做最小可运行入口，不实现真实业务命令。

建议命令结构：

- `pm --help`
- `pm version`
- `pm health check`

其中：

- `version` 用于验证打包和入口安装正常
- `health check` 第一批返回基础运行状态，不触发任何外部交易请求

### 7.2 启动流程

`main.py` 入口建议流程：

1. `Settings.load()`
2. `settings.validate_for_readonly()`
3. `configure_logging()`
4. 创建 Typer app
5. 注册基础命令

### 7.3 `health check` 输出设计

第一批的 `pm health check` 至少输出以下信息：

1. 当前 settings 模式
   - `readonly`
   - `trading`

2. 日志配置是否生效
   - 当前 `log_level`
   - 当前输出格式：`json` / `console`
   - logging 初始化是否成功

3. 数据库是否可连接
   - 若当前阶段未启用数据库检查，则返回 `disabled`
   - 若已启用数据库检查，则返回 `ok` / `failed`

建议输出结构：

```json
{
  "mode": "readonly",
  "logging": {
    "configured": true,
    "level": "INFO",
    "format": "console"
  },
  "database": {
    "enabled": true,
    "status": "ok"
  }
}
```

说明：

- 第一批允许数据库检查关闭，但默认设计目标是 PostgreSQL 可连接
- 但接口结构要先固定，避免后续 CLI 输出被破坏
- 当 `PM_ENABLE_TRADING=true` 时，`mode` 必须明确显示为 `trading`

### 7.4 测试用例

`tests/cli/test_cli_bootstrap.py`

至少覆盖：

1. `pm --help` 返回成功
2. `pm version` 返回版本信息
3. `pm health check` 返回成功
4. `pm health check` 包含 `mode`
5. `pm health check` 包含 logging 状态
6. `pm health check` 在数据库未启用时返回 `disabled`

---

## 8. 第一批交付验收标准

完成第一批后，应满足：

1. `pip install -e .` 可成功安装
2. `pm --help` 可运行
3. `.env.example` 可支撑只读模式启动
4. `Settings.load()` 与校验逻辑通过测试
5. logging 初始化通过测试
6. `pytest` 能执行并通过第一批测试
7. 若本地 PostgreSQL 可用，`pm health check` 可正确返回数据库连接状态

---

## 9. 第一批后的衔接

第一批完成后，第二批直接进入：

1. `GammaClient`
2. `MarketService.sync_markets`
3. `BookService.get_book`
4. CLI `markets sync`
5. CLI `book show`

这样可以保证在进入交易之前，先把只读数据链路打通。
