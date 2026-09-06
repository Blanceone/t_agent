# AI Quant Trading Agent 开发规格说明书

| 项目 | 内容 |
|:---|:---|
| 内部代号 | AI-T-Agent |
| 基于 PRD 版本 | V2.0 Final（Frozen） |
| SPEC 版本 | **V1.1 Final**（Frozen — Enter Development） |
| 开发阶段 | 第一阶段（稳定底座） |
| 开发顺序 | Trading Engine → Risk Engine → Scheduler → Replay → Memory → Decision → Reflection |
| 修订说明 | V1.1：基于 Final Review 补充开发准则、统一领域模型、错误码、Schema 版本注册、日志规范增强、事件定义增强、模块接口规范。冻结进入开发。 |

---

## 0. 开发准则（Development Principles）

本章为整个项目的最高开发准则，所有模块开发必须遵守。

| 编号 | 准则 | 说明 |
|:---|:---|:---|
| P1 | 稳定优先 | 优先保证系统稳定运行，而不是增加新功能 |
| P2 | 数据驱动 | 所有优化必须来源于模拟盘数据（Replay/日志/统计），而不是主观判断 |
| P3 | Rule 优先于 Prompt | Rule Engine 永远优先于 LLM；代码规则不可被 Prompt 覆盖 |
| P4 | Replay 是唯一依据 | Replay 是所有优化、Debug、验证的唯一可信数据源 |
| P5 | 单点迭代 | 一次版本只解决一个核心问题，避免同时修改多个模块 |
| P6 | 职责边界不可破坏 | 任何新增功能不得破坏 Rule + LLM 职责边界 |
| P7 | 版本管理 | PRD/SPEC 冻结后，所有变更通过 Version Iteration，禁止直接修改历史版本 |
| P8 | 禁止硬编码 | 所有 Magic Number 必须配置化，不得在代码中写死关键阈值 |
| P9 | 统一 Domain Model | 所有模块只使用统一领域模型，禁止大量 dict、重复定义、字段名不一致 |
| P10 | 不提前复杂化 | 不引入 Alpha Engine、多 Agent、新闻分析、复杂技术指标等未来版本内容 |

### Rule + LLM 职责边界（不可违反）

| 归属 | 模块 | 说明 |
|:---|:---|:---|
| **Rule（代码）** | Risk Engine / Trading Engine / Scheduler / Fee / Validation | 有唯一答案，代码为唯一真相源 |
| **LLM（模型）** | Planner / Decision / Reflection / Market Understanding | 需要判断，只能提建议 |
| **禁止** | LLM 直接参与风控、交易执行、账户修改 | LLM 不能直接交易，必经 Risk |

### 明确不做（当前版本）

- Alpha Engine / 复杂因子工厂
- Research Engine
- 多 Agent（Bull/Bear/Judge）
- 自动 Prompt 优化
- 新闻分析主路径
- 复杂技术指标（MACD/KDJ/ATR/布林带/Alpha101）
- 强化学习

---

## 1. 项目工程结构

```
ai-t-agent/
├── pyproject.toml                    # 项目元数据与依赖管理（推荐 poetry 或 hatch）
├── requirements.txt                  # 锁定依赖版本
├── .env.example                      # 环境变量模板（密钥、LLM API Key）
├── config/
│   ├── default.yaml                  # 默认配置（所有业务参数）
│   ├── dev.yaml                      # 开发环境覆盖
│   ├── prod.yaml                     # 生产环境覆盖
│   └── trading_calendar.json         # A股交易日历（含 session 字段）
├── prompts/
│   ├── decision_v1.0.md              # Decision Prompt 模板
│   ├── reflection_v1.0.md            # Reflection Prompt 模板
│   ├── planner_v1.0.md               # Planner Prompt 模板（第二阶段）
│   └── market_understanding_v1.0.md  # Market Understanding Prompt（第二阶段）
├── src/
│   └── agent/
│       ├── __init__.py
│       ├── main.py                   # 主入口：加载配置 → 初始化 → 启动 Scheduler
│       ├── config/
│       │   ├── __init__.py
│       │   ├── loader.py             # 配置加载器（YAML + 环境变量合并）
│       │   └── schema.py             # 配置 Pydantic Schema 定义
│       ├── trading/
│       │   ├── __init__.py
│       │   ├── engine.py             # TradingEngine 主类
│       │   ├── account.py            # Account / Cash / NAV 管理
│       │   ├── position.py           # Position 状态机
│       │   ├── order.py              # Order / Fill 模型
│       │   ├── matcher.py            # 撮合引擎（模拟盘零滑点）
│       │   ├── fee.py                # 费用计算器
│       │   ├── liquidation.py        # LiquidationWorker 清仓队列
│       │   ├── benchmark.py          # 基准组合（等权 + 沪深300）
│       │   └── settlement.py         # T+1 解冻 / 日切结算
│       ├── risk/
│       │   ├── __init__.py
│       │   ├── engine.py             # RiskEngine 主类
│       │   ├── state.py              # RiskState 状态机（NORMAL/HALT/LIQUIDATE）
│       │   ├── stop_loss.py          # 止损检测器
│       │   ├── position_limit.py     # 仓位/现金约束校验
│       │   └── confidence_filter.py  # 低置信度过滤
│       ├── scheduler/
│       │   ├── __init__.py
│       │   ├── scheduler.py          # Scheduler 主循环
│       │   ├── tick.py               # 单 Tick 原子执行流程
│       │   ├── calendar.py           # 交易日历服务
│       │   └── lifecycle.py          # 日切/开盘/休市/收盘生命周期
│       ├── replay/
│       │   ├── __init__.py
│       │   ├── store.py              # Replay 不可变存储
│       │   ├── runner.py             # Replay 回放执行器
│       │   ├── package.py            # Replay 包结构定义
│       │   └── evaluation.py         # 评估指标计算
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── store.py              # Memory 持久化存储
│       │   ├── writer.py             # Memory 写入（去重/冲突检测）
│       │   ├── retriever.py          # Memory 检索（Top-K）
│       │   ├── compressor.py         # Memory 压缩
│       │   └── models.py             # Memory 数据模型
│       ├── decision/
│       │   ├── __init__.py
│       │   ├── engine.py             # Decision 引擎（LLM 调用 + Schema 校验）
│       │   ├── context.py            # Context Assembler
│       │   ├── prompt.py             # Prompt 渲染器（版本管理）
│       │   └── validator.py          # Decision 输出 Schema 校验
│       ├── reflection/
│       │   ├── __init__.py
│       │   ├── stats.py              # 代码统计层（客观数值）
│       │   ├── analyzer.py           # LLM 解释层
│       │   └── report.py             # 日报生成
│       ├── market/
│       │   ├── __init__.py
│       │   ├── service.py            # 行情接入（tushare/akshare）
│       │   ├── feature.py            # Feature Engine（基础 Feature 预计算）
│       │   └── models.py             # 行情数据模型
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py             # LLM 统一调用客户端
│       │   ├── single_flight.py      # 单飞行控制器
│       │   └── schema_parser.py      # JSON Schema 解析与重试
│       ├── common/
│       │   ├── __init__.py
│       │   ├── event_log.py          # Event Log 统一事件日志
│       │   ├── logger.py             # 结构化日志（JSONL）
│       │   ├── models.py             # 公共数据模型（Enum/Base）
│       │   ├── errors.py             # 异常定义
│       │   └── utils.py              # 工具函数（时间、哈希等）
│       └── watchdog/
│           ├── __init__.py
│           └── watchdog.py           # WatchDog 进程监控
├── tests/
│   ├── conftest.py                   # 公共 Fixture
│   ├── unit/
│   │   ├── test_fee.py               # 费用计算精度测试
│   │   ├── test_t1.py                # T+1 制度测试
│   │   ├── test_position_state.py    # 持仓状态机测试
│   │   ├── test_risk_state.py        # 风控状态机测试
│   │   ├── test_stop_loss.py         # 止损逻辑测试
│   │   ├── test_confidence.py        # 置信度过滤测试
│   │   ├── test_liquidation.py       # 清仓跨日累计测试
│   │   ├── test_benchmark.py         # 基准清空重建测试
│   │   ├── test_memory.py            # Memory 跨日测试
│   │   └── test_context.py           # Context 组装测试
│   ├── integration/
│   │   ├── test_tick_flow.py         # 完整 Tick 流程集成测试
│   │   ├── test_day_lifecycle.py     # 日级生命周期测试
│   │   ├── test_replay.py            # Replay 可复现测试
│   │   └── test_reflection.py        # Reflection 统计一致性测试
│   └── acceptance/
│       ├── test_acceptance_01.py     # 验收标准 1-5
│       ├── test_acceptance_02.py     # 验收标准 6-10
│       └── test_acceptance_03.py     # 验收标准 11-15
├── scripts/
│   ├── init_calendar.py              # 生成交易日历
│   ├── seed_account.py               # 初始化模拟账户
│   └── run_replay.py                 # 手动触发 Replay
├── deploy/
│   ├── ai-t-agent.service            # systemd 主服务
│   ├── ai-t-agent-watchdog.service   # systemd WatchDog 服务
│   ├── install.sh                    # 部署脚本
│   └── backup.sh                     # 日终备份脚本
├── data/                             # 运行时数据（gitignore）
│   ├── account/                      # 账户快照
│   ├── memory/                       # Memory 存储
│   ├── replay/                       # Replay 包
│   ├── logs/                         # 日志文件
│   └── snapshots/                    # 每日备份
└── docs/
    ├── PRD_Personal_AI_Quant_Trading_Agent.md
    └── SPEC.md                       # 本文档
```

---

## 2. 第一阶段模块详细 SPEC

### 2.1 Trading Engine（交易引擎）

#### Purpose

负责账户真相管理、模拟撮合执行、A股费用结算、T+1制度执行、持仓状态机管理、清仓队列处理、基准组合维护。是系统物理层核心，所有有唯一答案的交易规则在此实现。

#### Input

| 输入 | 来源 | 说明 |
|:---|:---|:---|
| `OrderIntent` | Risk Engine 放行后 | 包含 action/code/shares/price/source |
| `Quote` | Market Service | 实时行情（bid1/ask1/last/limit_up/limit_down/is_suspended） |
| `UserCommand` | 用户指令接口 | ADD/REMOVE/CLEAR_ALL/PAUSE/RESUME/SET_CASH/STATUS（STATUS 只读：现价 + 最近10笔 `order_filled`） |
| `Config` | Config Center | 费用参数、仓位限制、清仓参数 |
| `TradingCalendar` | 日历文件 | 交易日判定、session 类型 |

#### Output

| 输出 | 消费者 | 说明 |
|:---|:---|:---|
| `Fill` | Account/Replay/EventLog | 成交记录（含费用明细） |
| `AccountSnapshot` | Risk/Decision/Context | 账户完整快照（NAV/持仓/现金） |
| `PositionStateChange` | EventLog/Memory | 状态迁移事件 |
| `RejectResult` | EventLog/Replay | 拒单记录（含原因码） |
| `BenchmarkSnapshot` | Reflection/Evaluation | 基准组合净值 |

#### Dependencies

- Config Center（费用参数、限制参数）
- Market Service（行情数据）
- Event Log（事件记录）
- 无上游业务模块依赖（最底层）

#### Processing

**2.1.1 核心类设计**

```python
# === account.py ===
@dataclass
class Cash:
    available: Decimal          # 可用现金
    reserved_min_ratio: float   # 最低现金预留比例（0.20）

@dataclass
class Account:
    account_id: str
    base_currency: str = "CNY"
    initial_cash: Decimal
    cash: Cash
    positions: Dict[str, Position]   # code -> Position
    watchlist: Dict[str, WatchlistEntry]
    risk_state: RiskState = RiskState.NORMAL
    last_nav_date: str               # 前一交易日日期
    last_nav: Decimal                # 前一交易日日终盯市净值
    peak_nav: Decimal                # 历史峰值净值
    liquidation_queue: List[LiquidationTask]
    benchmark: BenchmarkPortfolio
    realized_pnl_today: Decimal = Decimal("0")  # 当日累计已实现盈亏

    def nav_mark(self, quotes: Dict[str, Quote]) -> Decimal:
        """盯市净值 = cash.available + Σ(mark_price * total_shares)"""
        ...

    def snapshot(self) -> AccountSnapshot:
        """生成不可变快照用于 Tick 内决策"""
        ...

# === position.py ===
class PositionState(Enum):
    ACTIVE = "ACTIVE"
    PENDING_CLEAR = "PENDING_CLEAR"
    CLEARING = "CLEARING"
    LIQ_FAIL = "LIQ_FAIL"

@dataclass
class Position:
    code: str
    total_shares: int
    sellable_shares: int
    today_bought: int
    cost_price: Decimal
    stop_loss_price: Decimal         # cost_price * 0.92
    stop_breach_count: int = 0
    position_state: PositionState = PositionState.ACTIVE
    exit_reason: Optional[str] = None

    def on_day_start(self):
        """日切：T+1 解冻"""
        self.sellable_shares = self.total_shares
        self.today_bought = 0
        self.stop_breach_count = 0

    def apply_buy(self, shares: int, price: Decimal, fee: Decimal):
        """买入：加权平均成本法"""
        total_cost = self.cost_price * self.total_shares + price * shares + fee
        self.total_shares += shares
        self.today_bought += shares
        self.cost_price = total_cost / self.total_shares
        self.stop_loss_price = self.cost_price * Decimal("0.92")
        # 注意：sellable_shares 不增加（T+1）

    def apply_sell(self, shares: int, price: Decimal, fee: Decimal) -> Decimal:
        """卖出：返回已实现盈亏"""
        realized = (price - self.cost_price) * shares - fee
        self.total_shares -= shares
        self.sellable_shares -= shares
        return realized

# === fee.py ===
class FeeCalculator:
    """A股费用计算器（精度：Decimal，保留2位小数）"""
    STAMP_TAX_RATE = Decimal("0.0005")      # 印花税 0.05%（仅卖出）
    TRANSFER_FEE_RATE = Decimal("0.00001")  # 过户费 0.001%
    COMMISSION_RATE = Decimal("0.00025")    # 佣金万2.5
    MIN_COMMISSION = Decimal("5")           # 最低佣金5元

    def buy_fee(self, amount: Decimal) -> Decimal:
        commission = max(amount * self.COMMISSION_RATE, self.MIN_COMMISSION)
        transfer = amount * self.TRANSFER_FEE_RATE
        return (commission + transfer).quantize(Decimal("0.01"))

    def sell_fee(self, amount: Decimal) -> Decimal:
        commission = max(amount * self.COMMISSION_RATE, self.MIN_COMMISSION)
        transfer = amount * self.TRANSFER_FEE_RATE
        stamp_tax = amount * self.STAMP_TAX_RATE
        return (commission + transfer + stamp_tax).quantize(Decimal("0.01"))

    def round_trip_fee_est(self, price: Decimal, shares: int = 100) -> Decimal:
        """往返费用估算（用于 Feature 注入）"""
        amount = price * shares
        return self.buy_fee(amount) + self.sell_fee(amount)

# === matcher.py ===
class SimMatcher:
    """模拟撮合引擎（零滑点）"""

    def match(self, intent: OrderIntent, quote: Quote) -> MatchResult:
        """
        买入按 ask1，卖出按 bid1
        校验：涨跌停、停牌、最小交易单位、零股规则
        """
        ...

    def _validate_buy(self, intent, quote) -> Optional[RejectReason]:
        # ask1 >= limit_up → REASON_LIMIT_BOARD
        # is_suspended → REASON_SUSPENDED
        # shares % 100 != 0 → REASON_INVALID_LOT
        ...

    def _validate_sell(self, intent, quote, position) -> Optional[RejectReason]:
        # bid1 <= limit_down → REASON_LIMIT_BOARD
        # shares > sellable_shares → REASON_INSUFFICIENT_SELLABLE
        # 非清仓场景产生零股 → REASON_ODD_LOT
        ...

# === liquidation.py ===
class LiquidationWorker:
    """清仓队列消费者"""
    MAX_ATTEMPTS = 30  # 跨日累计，从 Config 读取

    def process_tick(self, queue: List[LiquidationTask], quotes: Dict[str, Quote]) -> List[Fill]:
        """每分钟消费清仓队列，拆单执行"""
        ...

    def _attempt_sell(self, task: LiquidationTask, quote: Quote) -> Optional[Fill]:
        """单次清仓尝试；失败则 task.attempts += 1"""
        ...

    def _check_exhausted(self, task: LiquidationTask) -> bool:
        """attempts >= MAX_ATTEMPTS → 标记 LIQ_FAIL"""
        ...

# === benchmark.py ===
class BenchmarkPortfolio:
    """基准组合管理"""

    def rebuild_equal_weight(self, watchlist: List[str], quotes: Dict[str, Quote], nav: Decimal):
        """watchlist 变更时：清空重建（非增量）"""
        # 按 pre_close 等权分配
        ...

    def update_daily(self, quotes: Dict[str, Quote], csi300_close: float):
        """日终重估"""
        ...

# === engine.py ===
class TradingEngine:
    """交易引擎主类：协调撮合、记账、状态管理"""

    def __init__(self, config, fee_calc, matcher, liquidation_worker, benchmark, event_log):
        ...

    def execute_order(self, intent: OrderIntent, quote: Quote) -> ExecutionResult:
        """执行一笔订单（Risk 已放行）"""
        ...

    def process_user_command(self, cmd: UserCommand) -> CommandResult:
        """处理用户指令"""
        ...

    def on_day_start(self, watchlist_changed: bool, quotes: Dict[str, Quote]):
        """日切：T+1解冻、基准重建、冷却清理"""
        ...

    def on_day_end(self, quotes: Dict[str, Quote]) -> DayEndSummary:
        """日终：计算 nav_mark、更新 peak_nav"""
        ...
```

**2.1.2 关键数据结构**

```python
@dataclass
class OrderIntent:
    intent_id: str
    action: Literal["BUY", "SELL"]
    code: str
    shares: int
    source: Literal["DECISION", "STOP_LOSS", "LIQUIDATE", "USER_REMOVE"]
    confidence: Optional[float] = None
    decision_id: Optional[str] = None

@dataclass
class Fill:
    fill_id: str
    order_id: str
    code: str
    action: str
    shares: int
    price: Decimal
    amount: Decimal
    fee: Decimal
    fee_detail: FeeDetail
    realized_pnl: Optional[Decimal]  # 卖出时
    timestamp: datetime
    tick_id: str

@dataclass
class FeeDetail:
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal

@dataclass
class LiquidationTask:
    task_id: str
    code: str
    remaining_shares: int
    exit_reason: str
    attempts: int = 0          # 跨日累计
    created_at: str = ""

class RejectReason(Enum):
    LIMIT_BOARD = "REASON_LIMIT_BOARD"
    NO_QUOTE = "REASON_NO_QUOTE"
    SUSPENDED = "REASON_SUSPENDED"
    INSUFFICIENT_SELLABLE = "REASON_INSUFFICIENT_SELLABLE"
    INVALID_LOT = "REASON_INVALID_LOT"
    ODD_LOT = "REASON_ODD_LOT"
    COOLDOWN = "REASON_COOLDOWN"
    CASH_RESERVE = "REASON_CASH_RESERVE"
    POSITION_LIMIT = "REASON_POSITION_LIMIT"
    HALT = "REASON_HALT"
    LOW_CONFIDENCE = "REASON_LOW_CONFIDENCE"
    STALE_QUOTE = "REASON_STALE_QUOTE"
```

**2.1.3 费用精度验收**

```
股价 2.00 元，100 股往返：
买入金额 = 200.00
  佣金 = max(200 * 0.00025, 5) = max(0.05, 5) = 5.00
  过户费 = 200 * 0.00001 = 0.002 → 0.00
卖出金额 = 200.00
  佣金 = max(200 * 0.00025, 5) = 5.00
  过户费 = 200 * 0.00001 = 0.002 → 0.00
  印花税 = 200 * 0.0005 = 0.10
总计 = 5.00 + 0.00 + 5.00 + 0.00 + 0.10 = 10.10 元
```

#### Failure Handling

| 异常场景 | 处理策略 |
|:---|:---|
| 行情字段缺失 | 拒绝撮合，返回 `REASON_NO_QUOTE`，记日志 |
| 行情时间戳偏差 > 5s | 拒绝，返回 `REASON_STALE_QUOTE` |
| 撮合异常（代码Bug） | 不修改账户状态，记 ERROR 日志，WatchDog 告警 |
| 清仓连续失败达30次 | 标记 `LIQ_FAIL`，禁止买入，告警等待人工介入 |
| 账户快照写入失败 | 重试1次；仍失败则阻断当前 Tick，WatchDog 介入 |

#### Logging

- `trade_log.jsonl`：每笔成交（fill_id/code/action/shares/price/fee/fee_detail/realized_pnl/tick_id/timestamp）
- `order_log.jsonl`：每笔订单意图与结果（含拒单原因码）
- 状态迁移事件写入 `event_log.jsonl`

#### Replay

- 每笔 Fill 关联 `tick_id`、`decision_id`、`context_id`
- 账户快照每分钟落盘（或变更时落盘），支持任意 Tick 回溯
- 清仓任务 `attempts` 计数持久化，跨日可审计

---

### 2.2 Risk Engine（风控引擎）

#### Purpose

保护账户安全。所有 LLM 决策必须经 Risk Engine 校验后才能进入 Trading Engine。实现三级风控状态机、止损检测、仓位约束、低置信度过滤。Risk 永远优先，不可绕过。

#### Input

| 输入 | 来源 | 说明 |
|:---|:---|:---|
| `OrderIntent` + `DecisionOutput` | Decision Engine | 待校验的交易意图 |
| `AccountSnapshot` | Trading Engine | 当前账户状态 |
| `Quote` | Market Service | 实时行情（止损判定） |
| `RiskState` | 内部状态 | NORMAL/HALT/LIQUIDATE |
| `Config` | Config Center | 所有风控阈值 |

#### Output

| 输出 | 消费者 | 说明 |
|:---|:---|:---|
| `RiskVerdict` | Trading Engine | PASS/REJECT + 原因码 |
| `RiskStateChanged` | EventLog/Context/Scheduler | 状态变更事件 |
| `StopLossTrigger` | Trading Engine (Liquidation) | 止损清仓指令 |
| `RiskSnapshot` | Context Assembler | 当前风控状态摘要 |

#### Dependencies

- Trading Engine（AccountSnapshot、执行清仓）
- Config Center（阈值参数）
- Event Log（事件记录）

#### Processing

**2.2.1 核心类设计**

```python
# === state.py ===
class RiskState(Enum):
    NORMAL = "NORMAL"
    HALT = "HALT"
    LIQUIDATE = "LIQUIDATE"

class RiskStateManager:
    """三级风控状态机"""

    def __init__(self, config):
        self.state = RiskState.NORMAL
        self.day_loss_halt_ratio = config.day_loss_halt_ratio        # 0.03
        self.realized_loss_halt_abs = config.realized_loss_halt_abs  # 500
        self.max_drawdown_liquidate = config.max_drawdown_liquidate  # 0.10

    def evaluate(self, snapshot: AccountSnapshot) -> RiskState:
        """每分钟 Tick 开始时评估"""
        # 1. LIQUIDATE 优先级最高
        drawdown = (snapshot.peak_nav - snapshot.nav_mark) / snapshot.peak_nav
        if drawdown >= self.max_drawdown_liquidate:
            return self._transition(RiskState.LIQUIDATE)

        # 2. HALT 判定
        day_loss = (snapshot.last_nav - snapshot.nav_mark) / snapshot.last_nav
        if day_loss >= self.day_loss_halt_ratio:
            return self._transition(RiskState.HALT)
        if snapshot.realized_pnl_today <= -self.realized_loss_halt_abs:
            return self._transition(RiskState.HALT)

        return self.state

    def on_day_start(self):
        """次日 09:20：HALT → NORMAL（LIQUIDATE 不自动恢复）"""
        if self.state == RiskState.HALT:
            self.state = RiskState.NORMAL

    def on_resume(self):
        """用户 RESUME 指令：HALT → NORMAL"""
        if self.state == RiskState.HALT:
            self.state = RiskState.NORMAL

# === stop_loss.py ===
class StopLossDetector:
    """止损检测器"""

    def __init__(self, config):
        self.stop_loss_ratio = config.stop_loss_ratio              # 0.92
        self.enable_deep = config.enable_deep_stop_loss            # False
        self.deep_threshold = Decimal("0.98")                      # 深度穿透系数
        self.breach_confirm_count = 2                              # 连续确认次数

    def check(self, position: Position, quote: Quote) -> StopLossResult:
        """
        返回：NONE / BREACH_INCREMENT / TRIGGER / DEEP_TRIGGER
        """
        trigger_price = quote.bid1 or quote.mark_price
        if trigger_price is None:
            return StopLossResult.NONE

        if trigger_price > position.stop_loss_price:
            position.stop_breach_count = 0  # 未触发则归零
            return StopLossResult.NONE

        # 深度穿透（开关开启时）
        if self.enable_deep:
            deep_price = position.stop_loss_price * self.deep_threshold
            if trigger_price <= deep_price:
                return StopLossResult.DEEP_TRIGGER  # 立即触发，无需等2分钟

        # 常规确认
        position.stop_breach_count += 1
        if position.stop_breach_count >= self.breach_confirm_count:
            return StopLossResult.TRIGGER

        return StopLossResult.BREACH_INCREMENT

# === confidence_filter.py ===
class ConfidenceFilter:
    """低置信度过滤器"""

    def __init__(self, config):
        self.threshold = config.decision_confidence_threshold  # 0.60

    def check(self, decision: DecisionItem) -> bool:
        """
        返回 True = 通过，False = 过滤
        仅对 BUY/SELL 生效；HOLD 不过滤
        风控强制单（止损/强平）不受此限制
        """
        if decision.action == "HOLD":
            return True
        if decision.source in ("STOP_LOSS", "LIQUIDATE"):
            return True
        confidence = decision.confidence if decision.confidence is not None else 0.0
        return confidence >= self.threshold

# === position_limit.py ===
class PositionLimitChecker:
    """仓位与资金约束"""

    def check_cash_reserve(self, snapshot, intent, quote) -> bool:
        """available_cash - (预买金额 + 预估费用) >= nav_mark * 20%"""
        ...

    def check_single_position(self, snapshot, intent, quote) -> bool:
        """mark_price * (total_shares + new_shares) <= nav_mark * 50%"""
        ...

    def check_cooldown(self, watchlist_entry, code) -> bool:
        """cooldown_until_date >= 当前日期 → 禁止 BUY"""
        ...

# === engine.py ===
class RiskEngine:
    """风控引擎主类"""

    def __init__(self, config, state_mgr, stop_loss_detector,
                 confidence_filter, position_checker, event_log):
        ...

    def tick_guard(self, snapshot: AccountSnapshot, quotes: Dict[str, Quote]) -> TickGuardResult:
        """
        每分钟 Tick 开始调用（优先级最高）：
        1. 评估风控状态（HALT/LIQUIDATE）
        2. 扫描所有持仓止损
        3. 返回需要执行的止损清仓列表
        """
        ...

    def validate_decision(self, decision: DecisionItem, snapshot: AccountSnapshot,
                          quote: Quote) -> RiskVerdict:
        """
        校验单条 Decision：
        1. confidence 过滤
        2. HALT 下禁止 BUY
        3. LIQUIDATE 下忽略所有
        4. 现金预留
        5. 单票上限
        6. 冷却期
        7. 涨跌停（委托 Trading Engine 撮合时校验）
        返回 PASS / REJECT(reason)
        """
        ...
```

**2.2.2 风控校验流水线（validate_decision 内部顺序）**

```
1. risk_state == LIQUIDATE → REJECT(REASON_HALT)  [实际由 Scheduler 跳过 LLM]
2. risk_state == HALT && action == BUY → REJECT(REASON_HALT)
3. confidence < threshold && source == DECISION → REJECT(REASON_LOW_CONFIDENCE)
4. action == BUY:
   a. 冷却期检查 → REJECT(REASON_COOLDOWN)
   b. 现金预留检查 → REJECT(REASON_CASH_RESERVE)
   c. 单票上限检查 → REJECT(REASON_POSITION_LIMIT)
5. action == SELL:
   a. sellable_shares 检查 → REJECT(REASON_INSUFFICIENT_SELLABLE)
6. PASS → 进入 Trading Engine 撮合
```

#### Failure Handling

| 异常场景 | 处理策略 |
|:---|:---|
| Risk Engine 自身异常 | **Fail-Closed**：禁止所有新开仓，允许已有清仓继续 |
| AccountSnapshot 获取失败 | 禁止所有操作，告警 |
| 配置加载失败 | 使用硬编码安全默认值（最严格），告警 |

#### Logging

- 所有拒单必须记录原因码至 `decision_log.jsonl`
- 风控状态变更写入 `event_log.jsonl`（含触发公式计算值）
- 止损触发记录：code/bid1/stop_loss_price/breach_count/deep_trigger

#### Replay

- `RiskSnapshot` 每分钟随 Tick 落盘
- 拒单原因码可追溯
- 止损 `stop_breach_count` 变化序列可回放

---

### 2.3 Scheduler（调度中心）

#### Purpose

全系统唯一调度中心，驱动日级生命周期与分钟级 Tick 循环。保证 Tick 内全同步原子执行，维护执行顺序不可变。

#### Input

| 输入 | 来源 | 说明 |
|:---|:---|:---|
| `TradingCalendar` | 日历文件 | 交易日/session 判定 |
| `Config` | Config Center | 超时、间隔参数 |
| 各模块就绪信号 | 内部 | 初始化完成 |

#### Output

| 输出 | 消费者 | 说明 |
|:---|:---|:---|
| Tick 触发信号 | 所有模块 | 每分钟原子执行 |
| 生命周期事件 | EventLog | DAY_START/SESSION_START/SESSION_SUSPEND/DAY_CLOSE |
| 调度状态 | WatchDog | 心跳、卡死检测 |

#### Dependencies

- Trading Engine（日切、执行）
- Risk Engine（Tick Guard）
- Decision Engine（LLM 决策）
- Market Service（行情）
- Reflection（日终）
- Replay Store（落盘）
- Event Log（事件）

#### Processing

**2.3.1 核心类设计**

```python
# === scheduler.py ===
class Scheduler:
    """唯一调度中心（单例）"""

    def __init__(self, config, calendar, trading_engine, risk_engine,
                 decision_engine, market_service, reflection, replay_store,
                 event_log, watchdog_heartbeat):
        self._running = False
        self._tick_lock = threading.Lock()  # Tick 内互斥

    def run(self):
        """主循环"""
        self._running = True
        while self._running:
            now = datetime.now()
            if not self.calendar.is_trading_day(now.date()):
                sleep(60)  # 非交易日休眠
                continue
            self._dispatch_by_time(now)

    def _dispatch_by_time(self, now: datetime):
        """根据时间分发任务"""
        t = now.time()
        if t == time(9, 20):
            self._on_day_start()
        elif self._in_trading_session(t):
            self._on_tick(now)
        elif t == time(14, 57):
            self._on_session_suspend()
        elif t == time(15, 5):
            self._on_day_close()

    def _in_trading_session(self, t) -> bool:
        """09:30-11:30 / 13:00-14:57"""
        am = time(9, 30) <= t <= time(11, 30)
        pm = time(13, 0) <= t <= time(14, 57)
        return am or pm

# === tick.py ===
class TickExecutor:
    """单 Tick 原子执行（全同步）"""

    def execute(self, tick_id: str, now: datetime):
        """
        严格顺序，不可并行，不可跳过：
        """
        with self._tick_lock:
            # Step 1: 锁定快照
            snapshot = self.trading_engine.account.snapshot()

            # Step 2: 行情检查
            quotes = self.market_service.get_quotes()
            if self._is_stale(quotes, now):
                self.event_log.emit("SKIP_STALE", tick_id)
                return

            # Step 3: RiskGuard 扫描（止损/HALT/LIQUIDATE）
            guard_result = self.risk_engine.tick_guard(snapshot, quotes)
            if guard_result.state_changed:
                snapshot = self.trading_engine.account.snapshot()  # 刷新快照

            # Step 4: LiquidationWorker
            self.trading_engine.liquidation_worker.process_tick(
                snapshot.liquidation_queue, quotes)

            # Step 5: 判断是否跳过 LLM
            if snapshot.risk_state == RiskState.LIQUIDATE:
                return  # 忽略 LLM
            if snapshot.risk_state == RiskState.HALT:
                pass  # 仅允许 SELL
            if self.system_mode == "PAUSE":
                return  # 跳过 LLM，清仓已在 Step 4 处理

            # Step 6: 组装 Context
            context = self.context_assembler.assemble(snapshot, quotes, ...)

            # Step 7: LLM Decision（单飞行）
            decision = self.decision_engine.decide(context, snapshot.risk_state)
            if decision is None:
                return  # 超时/失败，本分钟 HOLD

            # Step 8: Risk 校验 Decision
            for item in decision.decisions:
                verdict = self.risk_engine.validate_decision(item, snapshot, quotes[item.code])
                if verdict.passed:
                    # Step 9: Execution
                    self.trading_engine.execute_order(item.to_intent(), quotes[item.code])

            # Step 10: Save + Event Log
            self.trading_engine.persist()
            self.event_log.emit("TICK_FINISHED", tick_id)

# === lifecycle.py ===
class LifecycleManager:
    """日级生命周期管理"""

    def on_day_start(self):
        """09:20 日切"""
        # 1. T+1 解冻
        # 2. 清零 stop_breach_count
        # 3. 清理过期冷却
        # 4. 检查 PENDING_CLEAR / 未完成清仓
        # 5. 等权基准清空重建（若 watchlist 变更）
        # 6. HALT → NORMAL
        # 7. Market Understanding（第二阶段）
        # 8. Planner（第二阶段）
        self.event_log.emit("SCHEDULER_DAY_START")

    def on_session_suspend(self):
        """14:57 挂起"""
        # 停止决策与撮合
        # 进行中 LLM 输出丢弃
        # 未完成清仓挂起至次日
        self.event_log.emit("SESSION_SUSPEND")

    def on_day_close(self):
        """15:05 日终"""
        # 1. 计算 nav_mark，更新 peak_nav
        # 2. 代码统计 Reflection stats
        # 3. Reflection（LLM 解释）
        # 4. Memory Update
        # 5. 日报
        # 6. Replay 包落盘
        self.event_log.emit("DAY_CLOSE_FINISHED")
```

**2.3.2 时间轴精确控制**

| 时间 | 动作 | 优先级 |
|:---|:---|:---|
| 09:20:00 | 日切全流程 | P4 |
| 09:30:00 | 交易循环开始 | - |
| 每分钟 :00 | Tick 执行（约 1-30s，取决于 LLM） | P5 |
| 11:30:00 | 上午休市（保持状态） | - |
| 13:00:00 | 下午恢复 | - |
| 14:57:00 | 挂起（P1 最高优先级） | P1 |
| 15:05:00 | 日终流程 | P6 |

**2.3.3 单飞行控制**

```python
class SingleFlightGuard:
    """LLM 单飞行：上次未返回则本分钟跳过"""
    def __init__(self):
        self._in_flight = False

    def try_acquire(self) -> bool:
        if self._in_flight:
            return False
        self._in_flight = True
        return True

    def release(self):
        self._in_flight = False
```

#### Failure Handling

| 异常场景 | 处理策略 |
|:---|:---|
| Tick 执行超时（>60s） | 强制中断 LLM 等待，记 `TICK_TIMEOUT`，进入下一分钟 |
| Scheduler 主循环异常 | WatchDog 检测心跳超时后重启进程 |
| 恢复后状态 | 从最近落盘快照加载，不重放未确认成交 |
| 时钟漂移 | 使用 NTP 同步；Tick 触发允许 ±2s 容差 |

#### Logging

- `scheduler_log.jsonl`：每个 Tick 阶段耗时（ms）、跳过原因、风控变更
- `event_log.jsonl`：里程碑事件（见 Event Log 章节）

#### Replay

- 每个 Tick 的完整执行序列（阶段+耗时+结果）写入 Replay 包
- 可还原某日所有 Tick 的时序与决策链路

---

### 2.4 Replay & Evaluation（回放与评估）

#### Purpose

支持学习、Debug、收益分析。Replay 必须完全可复现：同输入同配置可完整复现决策与成交。记录完整决策链路（Prompt/Feature/Memory/Context/Confidence/Risk/Execution/Trade）。

#### Input

| 输入 | 来源 | 说明 |
|:---|:---|:---|
| 运行期全量事件流 | 所有模块 | Tick 级事件 |
| Account 快照序列 | Trading Engine | 每分钟/变更时 |
| Decision 日志 | Decision Engine | 含完整引用信息 |
| Config 版本 | Config Center | 运行时配置快照 |

#### Output

| 输出 | 消费者 | 说明 |
|:---|:---|:---|
| Replay Package | 离线分析/Debug | 不可变日级包 |
| Evaluation Report | 日报/周报 | 超额/回撤/费用/评分 |
| Replay Result | 对照验证 | 回放一致性报告 |

#### Dependencies

- 所有模块的日志/事件输出
- Config Center（配置快照）
- 文件系统（不可变存储）

#### Processing

**2.4.1 核心类设计**

```python
# === package.py ===
@dataclass
class ReplayPackage:
    """日级 Replay 包（schema: replay.v1）"""
    schema_version: str = "replay.v1"
    date: str
    config_snapshot: dict          # 当日运行配置
    calendar_info: dict            # 交易日信息
    ticks: List[TickRecord]        # 所有 Tick 记录
    day_summary: DaySummary        # 日终汇总
    memory_snapshot_ids: List[str] # 当日引用的 Memory IDs

@dataclass
class TickRecord:
    tick_id: str
    timestamp: str
    account_snapshot_hash: str
    quotes_snapshot: Dict[str, dict]    # 行情快照（或哈希）
    risk_state: str
    risk_guard_result: dict
    liquidation_actions: List[dict]
    context_id: str
    context_hash: str
    prompt_id: str
    prompt_version: str
    prompt_render_hash: str
    feature_snapshot: dict              # 输入 Feature
    feature_hash: str
    memory_ids: List[str]               # 注入的 Memory
    decision_output: Optional[dict]     # 完整 Decision JSON
    confidence: Optional[float]
    reason: Optional[str]
    risk_level: Optional[str]
    referenced_memory: List[str]
    market_regime: Optional[str]
    risk_verdicts: List[dict]           # 每条 Decision 的校验结果
    executions: List[dict]              # 成交记录
    latency_ms: dict                    # 各阶段耗时

# === store.py ===
class ReplayStore:
    """不可变 Replay 存储"""
    BASE_DIR = "data/replay"

    def save_daily_package(self, package: ReplayPackage):
        """日终落盘：data/replay/{date}/replay_package.json"""
        ...

    def save_tick(self, tick: TickRecord):
        """实时追加：data/replay/{date}/ticks.jsonl"""
        ...

    def load_package(self, date: str) -> ReplayPackage:
        """加载某日 Replay 包"""
        ...

# === runner.py ===
class ReplayRunner:
    """Replay 回放执行器"""

    def replay_day(self, date: str, config_override: dict = None) -> ReplayResult:
        """
        加载 Replay 包 → 用相同配置重放 → 对比结果
        用于验证：同输入同配置 → 同输出
        """
        ...

    def replay_decision(self, tick_id: str) -> DecisionReplayResult:
        """单独回放某条 Decision（含 Prompt/Feature/Memory 还原）"""
        ...

# === evaluation.py ===
class Evaluator:
    """评估指标计算"""

    def compute_daily(self, package: ReplayPackage) -> DailyEvaluation:
        return DailyEvaluation(
            nav=...,
            excess_vs_equal_weight=...,
            excess_vs_csi300=...,
            max_drawdown=...,
            fee_ratio=...,
            t_trading_pnl=...,
            halt_count=...,
            low_confidence_filter_count=...,
            decision_success_rate=...,
        )
```

**2.4.2 Replay 包目录结构**

```
data/replay/
└── 2026-07-28/
    ├── replay_package.json       # 完整日级包
    ├── ticks.jsonl               # Tick 级事件流
    ├── config_snapshot.yaml      # 当日配置
    ├── account_snapshots/        # 关键时点账户快照
    │   ├── 093000.json
    │   └── 150500.json
    └── context/                  # Context 快照
        ├── ctx_093100.json
        └── ctx_093200.json
```

#### Failure Handling

| 异常场景 | 处理策略 |
|:---|:---|
| Replay 写入失败 | 不阻断交易主循环；记 ERROR；日终重试补写 |
| Replay 包损坏 | 从 ticks.jsonl + snapshots 重建 |
| 磁盘空间不足 | 告警；保留最近 30 日，更早的压缩归档 |

#### Logging

- Replay 落盘事件写入 `event_log.jsonl`（`REPLAY_PACKAGE_SAVED`）
- 回放对照结果写入 `replay_log.jsonl`

#### Replay

本模块自身即为 Replay 基础设施。验收标准：同一 Replay 包重复回放，关键成交与风控事件 100% 一致。

---

### 2.5 Memory（记忆系统）

#### Purpose

建立 Agent 长期成长能力。Memory 必须长期保留，不能每天重新开始。支持多类型记忆的写入、检索、压缩、注入 Prompt，使决策可继承历史经验。

#### Input

| 输入 | 来源 | 说明 |
|:---|:---|:---|
| Reflection 候选条目 | Reflection | 日终产生 |
| 风控重大事件 | Risk Engine | STOP_LOSS/HALT/LIQUIDATE 即时写入 |
| 成交事件 | Trading Engine | 关键做T结果 |
| 检索请求 | Context Assembler | 按 code/日期/标签/Top-K |

#### Output

| 输出 | 消费者 | 说明 |
|:---|:---|:---|
| Memory Items (Top-K) | Context Assembler | 注入 Prompt |
| memory_ids | Decision/Replay | 可追溯引用 |
| 压缩摘要 | 长期存储 | 旧记忆压缩 |

#### Dependencies

- 文件系统/SQLite（持久化）
- LLM Client（摘要生成，可选）
- Config Center（top_k/max_tokens/compress_after_days）

#### Processing

**2.5.1 核心类设计**

```python
# === models.py ===
class MemoryType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    MARKET = "MARKET"
    PORTFOLIO = "PORTFOLIO"
    REFLECTION = "REFLECTION"
    TRADE = "TRADE"
    HOLDING = "HOLDING"

@dataclass
class MemoryItem:
    """schema: memory.v1"""
    memory_id: str              # mem_{date}_{seq}
    schema_version: str = "memory.v1"
    type: MemoryType
    codes: List[str]            # 关联标的
    created_at: str             # ISO 8601
    ttl_days: Optional[int]     # None = 永久
    tags: List[str]
    content: str
    source: str                 # reflection_v1 / risk_event / trade_result
    importance: float           # [0, 1]
    compressed: bool = False
    original_ref: Optional[str] = None  # 压缩前原始 ID

# === store.py ===
class MemoryStore:
    """Memory 持久化（SQLite + JSON 文件双写）"""
    DB_PATH = "data/memory/memory.db"
    FILE_PATH = "data/memory/items.jsonl"

    def write(self, item: MemoryItem) -> str:
        """写入（返回 memory_id）"""
        ...

    def query(self, codes: List[str] = None, types: List[MemoryType] = None,
              tags: List[str] = None, date_from: str = None,
              limit: int = 8) -> List[MemoryItem]:
        """检索 Top-K（按 importance + recency 排序）"""
        ...

    def load_all(self) -> List[MemoryItem]:
        """启动时全量加载（验证跨日可用）"""
        ...

    def archive(self, memory_id: str):
        """归档（不删除）"""
        ...

# === writer.py ===
class MemoryWriter:
    """Memory 写入器（含去重/冲突检测）"""

    def write_from_reflection(self, candidates: List[dict]) -> List[str]:
        """日终 Reflection 候选 → 去重 → 写入"""
        ...

    def write_risk_event(self, event_type: str, code: str, detail: dict):
        """风控事件即时写入"""
        ...

    def _dedup_check(self, content: str, codes: List[str]) -> bool:
        """相似度去重（简单文本匹配 + 同 code 同 tag 24h 内）"""
        ...

# === retriever.py ===
class MemoryRetriever:
    """Memory 检索器（供 Context Assembler 调用）"""

    def __init__(self, store, config):
        self.top_k = config.memory_top_k                    # 8
        self.max_tokens = config.memory_inject_max_tokens   # 1500

    def retrieve_for_decision(self, codes: List[str], date: str) -> MemoryContext:
        """为 Decision 检索相关 Memory"""
        items = self.store.query(codes=codes, limit=self.top_k)
        # 截断至 max_tokens
        return MemoryContext(items=items, memory_ids=[i.memory_id for i in items])

    def retrieve_for_reflection(self, date: str) -> MemoryContext:
        """为 Reflection 检索近期 Memory"""
        ...

# === compressor.py ===
class MemoryCompressor:
    """定期压缩旧记忆"""

    def compress_old(self, after_days: int = 30):
        """将超过 N 天的 SHORT/TRADE 细节压缩为摘要"""
        # 保留原始在 Replay 存储
        # 标记 compressed=True
        ...
```

**2.5.2 存储 Schema（SQLite）**

```sql
CREATE TABLE memory_items (
    memory_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL DEFAULT 'memory.v1',
    type TEXT NOT NULL,
    codes TEXT NOT NULL,           -- JSON array
    created_at TEXT NOT NULL,
    ttl_days INTEGER,
    tags TEXT,                     -- JSON array
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    compressed INTEGER DEFAULT 0,
    original_ref TEXT,
    archived INTEGER DEFAULT 0
);

CREATE INDEX idx_memory_codes ON memory_items(codes);
CREATE INDEX idx_memory_type ON memory_items(type);
CREATE INDEX idx_memory_created ON memory_items(created_at);
CREATE INDEX idx_memory_importance ON memory_items(importance DESC);
```

#### Failure Handling

| 异常场景 | 处理策略 |
|:---|:---|
| Memory 读写失败 | **不阻断交易主循环**；降级为空 Memory + 告警 |
| 存储文件损坏 | 从 JSONL 备份重建 SQLite |
| 检索超时 | 返回空列表，记 `MEMORY_RETRIEVE_TIMEOUT` |

#### Logging

- `memory_log.jsonl`：写入（memory_id/type/source）、检索命中（query/ids/count）、压缩、注入截断

#### Replay

- 每条 Decision 记录引用的 `memory_ids`
- Memory 写入事件可追溯至 Reflection/RiskEvent 源
- 压缩不删除原始（Replay 可查）

---

### 2.6 Decision（分钟级决策）

#### Purpose

在连续竞价有效时段，结合最新行情、Today Plan、Memory、Portfolio、Risk Snapshot，调用 LLM 输出交易意图（BUY/SELL/HOLD + confidence/reason/risk_level/referenced_memory）。所有输出必须经 Risk Engine 校验。

#### Input

| 输入 | 来源 | 说明 |
|:---|:---|:---|
| `Context`（统一上下文） | Context Assembler | System/Market/Portfolio/Holding/Memory |
| `RiskState` | Risk Engine | 当前风控状态 |
| `Today Plan` | Planner（第二阶段；第一阶段用默认） | 做T计划 |
| `Config` | Config Center | LLM 超时、Prompt 版本 |

#### Output

| 输出 | 消费者 | 说明 |
|:---|:---|:---|
| `DecisionOutput` | Risk Engine | 结构化决策（schema: decision.v1） |
| Decision 日志 | Replay/EventLog | 完整记录 |

#### Dependencies

- Context Assembler（统一上下文）
- LLM Client（模型调用）
- Risk Engine（状态输入）
- Memory Retriever（Memory Context）
- Feature Engine（基础 Feature）
- Config Center（Prompt 版本、超时）

#### Processing

**2.6.1 核心类设计**

```python
# === engine.py ===
class DecisionEngine:
    """分钟级 LLM 决策引擎"""

    def __init__(self, config, llm_client, context_assembler,
                 prompt_renderer, validator, single_flight, event_log):
        self.timeout_ms = config.llm_timeout_ms
        self.prompt_version = config.decision_prompt_version  # "decision.v1.0"

    def decide(self, context: Context, risk_state: RiskState) -> Optional[DecisionOutput]:
        """
        主决策流程：
        1. 校验有效时段（由 Scheduler 保证）
        2. 单飞行检查
        3. 渲染 Prompt（注入 Context 切片）
        4. 调用 LLM
        5. Schema 校验
        6. 失败重试 1 次
        7. 仍失败 → 返回 None（本分钟 HOLD）
        """
        if not self.single_flight.try_acquire():
            self.event_log.emit("DECISION_SKIPPED_SINGLE_FLIGHT")
            return None

        try:
            prompt = self.prompt_renderer.render(
                template_version=self.prompt_version,
                context=context,
                risk_state=risk_state
            )
            raw = self.llm_client.call(prompt, timeout_ms=self.timeout_ms)
            decision = self.validator.parse_and_validate(raw)

            if decision is None:
                # 重试 1 次
                raw = self.llm_client.call(prompt, timeout_ms=self.timeout_ms)
                decision = self.validator.parse_and_validate(raw)

            return decision
        except LLMTimeoutError:
            self.event_log.emit("LLM_TIMEOUT")
            return None
        finally:
            self.single_flight.release()

# === context.py ===
class ContextAssembler:
    """统一上下文组装器（schema: context.v1）"""

    def assemble(self, snapshot: AccountSnapshot, quotes: Dict[str, Quote],
                 features: Dict[str, FeatureSet], memory_ctx: MemoryContext,
                 risk_snapshot: RiskSnapshot, today_plan: Optional[dict],
                 market_regime: Optional[str]) -> Context:
        """
        组装完整 Context：
        - system: 日期/时段/risk_state/模式/schema_version/配置摘要
        - market: 指数/regime/量能（第一阶段简化）
        - portfolio: nav_mark/现金/当日盈亏/基准超额
        - holdings: 每只票的持仓/可卖/成本/止损距/Feature
        - memory: Top-K 摘要 + memory_ids
        """
        ctx = Context(
            context_id=f"ctx_{date}_{time}",
            schema_version="context.v1",
            system=self._build_system(snapshot, risk_snapshot),
            market=self._build_market(quotes, market_regime),
            portfolio=self._build_portfolio(snapshot),
            holdings=self._build_holdings(snapshot, features),
            memory=memory_ctx,
        )
        # 长度截断
        ctx = self._truncate_to_budget(ctx)
        return ctx

# === prompt.py ===
class PromptRenderer:
    """Prompt 渲染器（版本管理）"""

    def render(self, template_version: str, context: Context,
               risk_state: RiskState) -> RenderedPrompt:
        """
        1. 加载模板文件 prompts/{template_version}.md
        2. 注入 Context 切片（非全量）
        3. 注入 risk_state（HALT 时特殊指令）
        4. 计算 render_hash
        5. 返回 RenderedPrompt(text, prompt_id, version, hash)
        """
        ...

# === validator.py ===
class DecisionValidator:
    """Decision 输出 Schema 校验（schema: decision.v1）"""

    def parse_and_validate(self, raw: str) -> Optional[DecisionOutput]:
        """
        1. JSON 解析（容错：提取 ```json 块）
        2. 字段校验：
           - action ∈ {BUY, SELL, HOLD}
           - confidence ∈ [0, 1]，缺失/非法 → 0
           - reason 非空
           - risk_level ∈ {LOW, MEDIUM, HIGH}，缺失 → MEDIUM
           - referenced_memory 为数组
           - shares >= 0，BUY 时 100 整数倍
        3. 校验失败 → None
        """
        ...
```

**2.6.2 Decision 输出数据结构**

```python
@dataclass
class DecisionOutput:
    schema_version: str = "decision.v1"
    thought_process: str
    decisions: List[DecisionItem]
    prompt_id: str
    prompt_version: str
    prompt_render_hash: str
    context_id: str
    timestamp: str

@dataclass
class DecisionItem:
    action: Literal["BUY", "SELL", "HOLD"]
    code: str
    shares: int
    confidence: float           # [0, 1]
    reason: str
    risk_level: str             # LOW/MEDIUM/HIGH
    referenced_memory: List[str]
```

**2.6.3 第一阶段简化处理**

- Market Understanding / Planner 在第二阶段实现
- 第一阶段：`market_regime` 默认 `RANGE`，`today_plan` 使用保守默认（低做T频率、禁止追涨）
- Context 中 market 部分仅注入指数涨跌、持仓涨跌分布

#### Failure Handling

| 异常场景 | 处理策略 |
|:---|:---|
| LLM 超时 | 本分钟跳过，记 `LLM_TIMEOUT` |
| Schema 非法 | 重试 1 次；仍失败 → HOLD |
| confidence 缺失/非法 | 视为 0（由 Risk 过滤） |
| referenced_memory 含未注入 ID | 剔除非法 ID，记 WARNING |
| 14:57 后 LLM 返回 | 丢弃输出 |
| Context 组装失败 | 使用最小降级 Context（System + Portfolio） |

#### Logging

- `decision_log.jsonl`：时间/risk_state_snapshot/context_id/prompt_version/feature_hash/memory_ids/输出JSON/校验结果/拒单原因

#### Replay

- 通过 `context_id` 可还原当时注入内容
- 通过 `prompt_render_hash` 可验证 Prompt 一致性
- `referenced_memory` 支持 Memory 变更前后对照

---

### 2.7 Reflection（日终复盘）

#### Purpose

先由代码产出客观统计（不依赖 LLM），再由 LLM 解释归因，提出 Memory/Prompt 更新建议。统计归代码，解释归 LLM。禁止仅用 LLM 口头编造关键数值。

#### Input

| 输入 | 来源 | 说明 |
|:---|:---|:---|
| 当日全部 Fill | Trading Engine | 成交记录 |
| AccountSnapshot（日初/日终） | Trading Engine | NAV 变化 |
| Decision 日志 | Decision Engine | 决策质量统计 |
| Risk 事件 | Risk Engine | HALT/止损/拒单 |
| Benchmark | Trading Engine | 基准对比 |
| Config | Config Center | - |

#### Output

| 输出 | 消费者 | 说明 |
|:---|:---|:---|
| `ReflectionStats` | 日报/Replay | 代码统计（客观） |
| `ReflectionAnalysis` | Memory/日报 | LLM 解释 |
| `MemoryCandidates` | Memory Writer | 待写入记忆 |
| 日报 | 用户/Replay | 结构化报告 |

#### Dependencies

- Trading Engine（成交/账户数据）
- Decision Engine（决策日志）
- Risk Engine（风控事件）
- Memory（检索近期记忆供 LLM 参考）
- LLM Client（解释层）

#### Processing

**2.7.1 核心类设计**

```python
# === stats.py ===
class ReflectionStatsCalculator:
    """代码统计层（15:05 第一步，不依赖 LLM）"""

    def compute(self, fills: List[Fill], snapshot_start: AccountSnapshot,
                snapshot_end: AccountSnapshot, decisions: List[DecisionOutput],
                risk_events: List[RiskEvent], benchmark: BenchmarkSnapshot,
                set_cash_events: List[SetCashEvent]) -> ReflectionStats:
        return ReflectionStats(
            day_pnl=snapshot_end.nav_mark - snapshot_start.nav_mark,
            fee_ratio=total_fees / snapshot_end.nav_mark,
            t_trading_pnl=self._calc_t_pnl(fills),
            holdings_mark_pnl=self._calc_holdings_pnl(snapshot_start, snapshot_end),
            sold_too_early_count=self._count_sold_early(fills, quotes_after),
            stop_loss_count=len([e for e in risk_events if e.type == "STOP_LOSS"]),
            halt_count=len([e for e in risk_events if e.type == "HALT"]),
            reject_count=len([e for e in risk_events if e.type == "REJECT"]),
            avg_holding_minutes=self._calc_avg_holding(fills),
            decision_success_rate=self._calc_success_rate(decisions, fills),
            low_confidence_hold_count=self._count_low_confidence(risk_events),
            set_cash_effect=self._calc_set_cash_effect(set_cash_events),
            excess_vs_equal_weight=...,
            excess_vs_csi300=...,
        )

    def _calc_t_pnl(self, fills: List[Fill]) -> Decimal:
        """做T收益 = 当日所有 SELL 的 realized_pnl 之和"""
        ...

# === analyzer.py ===
class ReflectionAnalyzer:
    """LLM 解释层"""

    def analyze(self, stats: ReflectionStats, memory_ctx: MemoryContext,
                context: Context) -> ReflectionAnalysis:
        """
        1. 将 stats 注入 Reflection Prompt
        2. LLM 输出：what_worked / what_failed / pnl_attribution /
           memory_candidates / prompt_change_suggestions / score
        3. Schema 校验
        4. 失败 → 仅保留 stats，analysis 标记为降级
        """
        ...

# === report.py ===
class DailyReportGenerator:
    """日报生成"""

    def generate(self, stats: ReflectionStats, analysis: ReflectionAnalysis,
                 benchmark: BenchmarkSnapshot) -> DailyReport:
        """
        包含：
        - 净值曲线数据
        - 基准对比（等权/沪深300）
        - 拒单率、费用率
        - 做T贡献
        - 低置信度过滤次数
        - SET_CASH 高亮标记
        - LLM 归因解释
        """
        ...
```

**2.7.2 Reflection 输出数据结构**

```python
@dataclass
class ReflectionStats:
    """代码统计（客观层）"""
    day_pnl: Decimal
    fee_ratio: float
    t_trading_pnl: Decimal
    holdings_mark_pnl: Decimal
    sold_too_early_count: int
    stop_loss_count: int
    halt_count: int
    reject_count: int
    avg_holding_minutes: float
    decision_success_rate: float
    low_confidence_hold_count: int
    set_cash_effect: Decimal
    excess_vs_equal_weight: Decimal
    excess_vs_csi300: Decimal

@dataclass
class ReflectionAnalysis:
    """LLM 解释层"""
    what_worked: List[str]
    what_failed: List[str]
    pnl_attribution: dict
    memory_candidates: List[dict]
    prompt_change_suggestions: List[str]
    score: dict    # decision_quality / risk_discipline
```

#### Failure Handling

| 异常场景 | 处理策略 |
|:---|:---|
| 统计数据与账本不一致 | 以账本为准；记 ERROR；告警 |
| LLM 解释失败 | 仅输出 stats 层；analysis 标记 `DEGRADED` |
| Memory 写入失败 | 候选条目暂存文件；次日重试 |

#### Logging

- `reflection_log.jsonl`：stats 全量 + analysis 摘要 + 耗时
- 日报输出至 `data/reports/{date}_daily.json`

#### Replay

- Reflection stats 可从 Fill 序列完全重算（确定性）
- LLM 分析记录 prompt_version + input_hash
- Memory 候选与最终写入可对照

---

## 3. 数据模型设计

### 3.1 核心实体关系

```
Account (1) ──── (N) Position
Account (1) ──── (1) Cash
Account (1) ──── (1) BenchmarkPortfolio
Account (1) ──── (N) LiquidationTask

Position (1) ──── (N) Order
Order (1) ──── (0..1) Fill

Decision (1) ──── (N) DecisionItem
DecisionItem ──── RiskVerdict ──── OrderIntent ──── Order ──── Fill

MemoryItem (N) ──── (N) Position (via codes)
ReplayPackage (1) ──── (N) TickRecord
```

### 3.2 持久化方案

| 数据 | 存储方式 | 说明 |
|:---|:---|:---|
| Account 状态 | JSON 文件（`data/account/state.json`） | 每次变更落盘；启动时加载 |
| Position | 内嵌于 Account JSON | 与 Account 原子更新 |
| Fill/Order 历史 | JSONL（`data/logs/trade_log.jsonl`） | 追加写 |
| Memory | SQLite + JSONL 双写 | 查询用 SQLite；备份用 JSONL |
| Replay 包 | JSON 文件（按日目录） | 不可变 |
| 配置 | YAML 文件 | 版本化 |
| 交易日历 | JSON 文件 | 年度更新 |
| Event Log | JSONL（`data/logs/event_log.jsonl`） | 追加写 |
| 日报 | JSON（`data/reports/`） | 按日 |

### 3.3 Account 持久化 Schema

```json
{
  "schema_version": "account.v1",
  "account_id": "sim_001",
  "saved_at": "2026-07-28T15:05:00+08:00",
  "base_currency": "CNY",
  "initial_cash": 30000.00,
  "cash": { "available": 12000.00, "reserved_min_ratio": 0.20 },
  "positions": {
    "600584": {
      "code": "600584",
      "total_shares": 1000,
      "sellable_shares": 800,
      "today_bought": 200,
      "cost_price": 28.00,
      "stop_loss_price": 25.76,
      "stop_breach_count": 0,
      "position_state": "ACTIVE",
      "exit_reason": null
    }
  },
  "watchlist": {
    "600584": { "added_at": "2026-07-01", "cooldown_until_date": null }
  },
  "risk_state": "NORMAL",
  "last_nav_date": "2026-07-25",
  "last_nav": 30000.00,
  "peak_nav": 30500.00,
  "realized_pnl_today": 0.00,
  "liquidation_queue": [],
  "benchmark": {
    "equal_weight": { "nav": 30000.00, "constituents": {}, "last_rebuild_date": "" },
    "csi300": { "nav": 30000.00, "index_value": 3500.0, "last_index_close": 3500.0 }
  }
}
```

---

## 3A. 统一领域模型（Domain Model）

所有模块只能使用以下统一 Domain Model。禁止使用裸 dict 传递业务数据、禁止重复定义、禁止字段名不一致。

实现位置：`src/agent/common/models.py`

### 核心实体定义

```python
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Literal

# ==================== 枚举 ====================

class RiskState(Enum):
    NORMAL = "NORMAL"
    HALT = "HALT"
    LIQUIDATE = "LIQUIDATE"

class PositionState(Enum):
    ACTIVE = "ACTIVE"
    PENDING_CLEAR = "PENDING_CLEAR"
    CLEARING = "CLEARING"
    LIQ_FAIL = "LIQ_FAIL"

class ActionType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class OrderSource(Enum):
    DECISION = "DECISION"
    STOP_LOSS = "STOP_LOSS"
    LIQUIDATE = "LIQUIDATE"
    USER_REMOVE = "USER_REMOVE"

class MemoryType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    MARKET = "MARKET"
    PORTFOLIO = "PORTFOLIO"
    REFLECTION = "REFLECTION"
    TRADE = "TRADE"
    HOLDING = "HOLDING"

class MarketRegime(Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOL = "HIGH_VOL"
    LOW_VOL = "LOW_VOL"

# ==================== 行情与 Feature ====================

@dataclass(frozen=True)
class Quote:
    """实时行情快照"""
    code: str
    name: str
    last: Decimal
    bid1: Optional[Decimal]
    ask1: Optional[Decimal]
    high: Decimal
    low: Decimal
    open: Decimal
    pre_close: Decimal
    limit_up: Decimal
    limit_down: Decimal
    volume: int
    turnover: Decimal
    vwap: Decimal
    is_suspended: bool
    is_st: bool
    timestamp: datetime

    @property
    def mark_price(self) -> Decimal:
        """盯市价格回退：bid1 → last → pre_close"""
        return self.bid1 or self.last or self.pre_close

@dataclass(frozen=True)
class FeatureSnapshot:
    """基础市场 Feature（schema: feature.v1）"""
    schema_version: str = "feature.v1"
    code: str
    pre_close: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    last: Decimal
    open_chg_pct: float
    chg_pct_1d: float
    chg_pct_5d: Optional[float]
    chg_pct_10d: Optional[float]
    vwap: Decimal
    amplitude: float
    volume: int
    volume_ratio: Optional[float]
    turnover_rate: Optional[float]
    round_trip_fee_est: Decimal

# ==================== 账户与持仓 ====================

@dataclass
class Position:
    """持仓实体"""
    code: str
    total_shares: int
    sellable_shares: int
    today_bought: int
    cost_price: Decimal
    stop_loss_price: Decimal
    stop_breach_count: int = 0
    position_state: PositionState = PositionState.ACTIVE
    exit_reason: Optional[str] = None

@dataclass
class AccountSnapshot:
    """账户不可变快照（Tick 内使用）"""
    account_id: str
    nav_mark: Decimal
    cash_available: Decimal
    peak_nav: Decimal
    last_nav: Decimal
    risk_state: RiskState
    positions: Dict[str, Position]
    realized_pnl_today: Decimal
    liquidation_queue: List['LiquidationTask']
    snapshot_time: datetime

# ==================== 订单与成交 ====================

@dataclass
class OrderIntent:
    """订单意图（Risk 校验前）"""
    intent_id: str
    action: ActionType
    code: str
    shares: int
    source: OrderSource
    confidence: Optional[float] = None
    decision_id: Optional[str] = None

@dataclass
class Fill:
    """成交记录"""
    fill_id: str
    order_id: str
    code: str
    action: ActionType
    shares: int
    price: Decimal
    amount: Decimal
    fee: Decimal
    fee_detail: 'FeeDetail'
    realized_pnl: Optional[Decimal]
    timestamp: datetime
    tick_id: str

@dataclass
class FeeDetail:
    """费用明细"""
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal

@dataclass
class LiquidationTask:
    """清仓任务"""
    task_id: str
    code: str
    remaining_shares: int
    exit_reason: str
    attempts: int = 0
    created_at: str = ""

# ==================== 决策 ====================

@dataclass
class DecisionItem:
    """单条决策（schema: decision.v1）"""
    action: ActionType
    code: str
    shares: int
    confidence: float
    reason: str
    risk_level: str  # LOW/MEDIUM/HIGH
    referenced_memory: List[str] = field(default_factory=list)

@dataclass
class DecisionOutput:
    """完整决策输出"""
    schema_version: str = "decision.v1"
    thought_process: str
    decisions: List[DecisionItem]
    prompt_id: str = ""
    prompt_version: str = ""
    prompt_render_hash: str = ""
    context_id: str = ""
    timestamp: str = ""

# ==================== 风控 ====================

@dataclass
class RiskVerdict:
    """风控校验结果"""
    passed: bool
    reason_code: Optional[str] = None
    detail: Optional[str] = None

@dataclass
class RiskSnapshot:
    """风控状态快照（注入 Context）"""
    risk_state: RiskState
    day_loss_ratio: float
    drawdown_ratio: float
    realized_pnl_today: Decimal
    halt_count_today: int
    stop_loss_count_today: int

# ==================== 记忆 ====================

@dataclass
class MemoryItem:
    """记忆条目（schema: memory.v1）"""
    memory_id: str
    schema_version: str = "memory.v1"
    type: MemoryType
    codes: List[str]
    created_at: str
    ttl_days: Optional[int]
    tags: List[str]
    content: str
    source: str
    importance: float
    compressed: bool = False
    original_ref: Optional[str] = None

# ==================== Replay ====================

@dataclass
class TickRecord:
    """单 Tick 完整记录（schema: replay.v1）"""
    tick_id: str
    timestamp: str
    account_snapshot_hash: str
    quotes_snapshot: Dict[str, dict]
    risk_state: str
    context_id: str
    prompt_id: str
    prompt_version: str
    prompt_render_hash: str
    feature_snapshot: dict
    feature_hash: str
    memory_ids: List[str]
    decision_output: Optional[dict]
    confidence: Optional[float]
    reason: Optional[str]
    risk_level: Optional[str]
    referenced_memory: List[str]
    market_regime: Optional[str]
    risk_verdicts: List[dict]
    executions: List[dict]
    latency_ms: dict
```

### Domain Model 使用规则

| 规则 | 说明 |
|:---|:---|
| 禁止裸 dict | 模块间传递业务数据必须使用上述 dataclass，禁止 `dict` |
| 禁止重复定义 | 各模块不得自行定义同名结构，统一从 `common/models.py` 导入 |
| 字段名一致 | 同一概念在所有模块中字段名必须相同（如 `nav_mark` 不得写为 `navMark`） |
| 不可变快照 | `Quote`、`FeatureSnapshot` 使用 `frozen=True`，Tick 内不可篡改 |
| 金额精度 | 所有金额/价格字段使用 `Decimal`，禁止 `float` |
| Schema 版本 | 涉及持久化的实体必须携带 `schema_version` 字段 |

---

## 4. 配置管理方案

### 4.1 配置层次

```
环境变量（.env）       → 密钥、环境标识（LLM_API_KEY, ENV=prod）
config/default.yaml   → 所有业务参数默认值
config/{env}.yaml     → 环境覆盖（dev/prod）
运行时 Config 对象     → Pydantic 校验后的不可变配置
```

### 4.2 配置 Schema（Pydantic）

```python
# === config/schema.py ===
from pydantic import BaseModel, Field
from decimal import Decimal

class FeeConfig(BaseModel):
    stamp_tax_rate: Decimal = Decimal("0.0005")
    transfer_fee_rate: Decimal = Decimal("0.00001")
    commission_rate: Decimal = Decimal("0.00025")
    min_commission: Decimal = Decimal("5")

class RiskConfig(BaseModel):
    stop_loss_ratio: Decimal = Decimal("0.92")
    enable_deep_stop_loss: bool = False
    deep_stop_loss_threshold: Decimal = Decimal("0.98")
    stop_breach_confirm_count: int = 2
    day_loss_halt_ratio: Decimal = Decimal("0.03")
    realized_loss_halt_abs: Decimal = Decimal("500")
    max_drawdown_liquidate: Decimal = Decimal("0.10")
    reserved_min_cash_ratio: Decimal = Decimal("0.20")
    max_single_position_ratio: Decimal = Decimal("0.50")
    decision_confidence_threshold: float = 0.60
    enforce_intraday_buy_limit: bool = False

class TradingConfig(BaseModel):
    initial_cash: Decimal = Decimal("30000")
    watchlist_limit: int = 20
    max_liquidation_attempts: int = 30
    max_liquidation_shares_per_tick: int = 10000
    stale_quote_threshold_sec: int = 5

class SchedulerConfig(BaseModel):
    tick_interval_sec: int = 60
    day_start_time: str = "09:20"
    session_am_start: str = "09:30"
    session_am_end: str = "11:30"
    session_pm_start: str = "13:00"
    session_pm_end: str = "14:57"
    day_close_time: str = "15:05"

class LLMConfig(BaseModel):
    provider: str = "openai"           # openai / azure / local
    model: str = "gpt-4o"
    api_key_env: str = "LLM_API_KEY"   # 环境变量名
    timeout_ms: int = 30000
    max_retries: int = 1
    temperature: float = 0.1

class PromptConfig(BaseModel):
    decision_version: str = "decision.v1.0"
    reflection_version: str = "reflection.v1.0"
    planner_version: str = "planner.v1.0"
    market_understanding_version: str = "market_understanding.v1.0"

class MemoryConfig(BaseModel):
    memory_top_k: int = 8
    memory_inject_max_tokens: int = 1500
    memory_compress_after_days: int = 30
    db_path: str = "data/memory/memory.db"

class MarketConfig(BaseModel):
    data_source: str = "akshare"       # akshare / tushare
    tushare_token_env: str = "TUSHARE_TOKEN"

class FeatureConfig(BaseModel):
    """基础 Feature 计算参数"""
    volume_ratio_lookback_days: int = 5       # 量比回看天数
    chg_pct_5d_lookback: int = 5              # 5日涨跌幅回看
    chg_pct_10d_lookback: int = 10            # 10日涨跌幅回看
    round_trip_est_shares: int = 100          # 往返费用估算股数

class DecisionConfig(BaseModel):
    """决策引擎参数"""
    confidence_threshold: float = 0.60        # 低置信度过滤阈值
    max_decision_retries: int = 1             # Schema 失败重试次数
    context_max_tokens: int = 4000            # Context 注入上限
    hold_on_failure: bool = True              # 失败时默认 HOLD

class ReplayConfig(BaseModel):
    """回放与评估参数"""
    retention_days: int = 90                  # Replay 包保留天数
    compress_after_days: int = 30             # 压缩归档阈值
    save_tick_realtime: bool = True           # 实时追加 Tick
    evaluation_benchmark: str = "equal_weight"  # 默认基准

class ReflectionConfig(BaseModel):
    """复盘参数"""
    enable_llm_analysis: bool = True          # 是否启用 LLM 解释层
    max_memory_candidates: int = 5            # 每次复盘最多产生 Memory 候选数

# === 配置化强制原则 ===
# 以下参数绝对禁止硬编码，必须从 Config 读取：
# - 所有风控阈值（止损/HALT/LIQUIDATE/confidence）
# - 费用参数（费率/最低佣金）
# - 调度时间（Tick间隔/并盘时间/收盘时间）
# - Memory 参数（TopK/MaxTokens/压缩天数）
# - Replay 参数（保留天数/压缩阈值）
# - LLM 参数（超时/模型/温度）

class AppConfig(BaseModel):
    """顶层配置"""
    env: str = "dev"
    fee: FeeConfig = FeeConfig()
    risk: RiskConfig = RiskConfig()
    trading: TradingConfig = TradingConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    llm: LLMConfig = LLMConfig()
    prompt: PromptConfig = PromptConfig()
    memory: MemoryConfig = MemoryConfig()
    market: MarketConfig = MarketConfig()
    feature: FeatureConfig = FeatureConfig()
    decision: DecisionConfig = DecisionConfig()
    replay: ReplayConfig = ReplayConfig()
    reflection: ReflectionConfig = ReflectionConfig()
    log_level: str = "INFO"
    data_dir: str = "data"
```

### 4.3 配置加载流程

```python
# === config/loader.py ===
def load_config(env: str = None) -> AppConfig:
    """
    1. 读取 config/default.yaml
    2. 读取 config/{env}.yaml 覆盖
    3. 环境变量覆盖（仅密钥类）
    4. Pydantic 校验
    5. 返回不可变 AppConfig
    """
    ...
```

### 4.4 配置审计

- 每日日终将当前配置快照写入 Replay 包
- 配置变更通过 Git 版本管理追踪
- 运行时不允许热更新关键风控参数（需重启）

---

## 5. 日志与事件系统

### 5.1 日志架构与统一规范

**统一日志级别：**

| 级别 | 使用场景 |
|:---|:---|
| `DEBUG` | 开发调试信息（生产默认关闭） |
| `INFO` | 正常业务事件（Tick完成、成交、Memory写入） |
| `WARNING` | 可恢复异常（LLM重试、行情缺失单次、Memory截断） |
| `ERROR` | 不可恢复异常（Schema校验失败、账户写入失败） |
| `CRITICAL` | 系统级故障（WatchDog重启、磁盘写满、账户不一致） |

**统一日志格式（每条必须包含）：**

```json
{
  "timestamp": "2026-07-28T09:31:02.345+08:00",
  "module": "risk",
  "level": "INFO",
  "event": "RISK_REJECTED",
  "message": "BUY rejected: confidence 0.45 < threshold 0.60",
  "tick_id": "tick_20260728_093100",
  "decision_id": "dec_20260728_093100_001",
  "replay_id": "replay_20260728",
  "request_id": "req_a1b2c3d4",
  "detail": {}
}
```

| 字段 | 必须 | 说明 |
|:---|:---|:---|
| `timestamp` | ✓ | ISO 8601 + 时区 |
| `module` | ✓ | 产生模块（scheduler/market/feature/decision/risk/trading/memory/replay/reflection） |
| `level` | ✓ | 日志级别 |
| `event` | ✓ | 事件类型（对应 SystemEvent 枚举） |
| `message` | ✓ | 人类可读描述 |
| `tick_id` | 交易时段必须 | 当前 Tick 标识 |
| `decision_id` | Decision 相关必须 | 决策唯一标识 |
| `replay_id` | ✓ | 当日 Replay 包标识 |
| `request_id` | LLM 调用必须 | 单次请求追踪 ID |
| `detail` | 可选 | 结构化补充信息 |

**日志配置实现：**

```python
# === common/logger.py ===
import structlog

def setup_logging(config: AppConfig):
    """统一结构化日志配置"""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.contextvars.merge_contextvars,  # 支持 tick_id/decision_id 上下文
            structlog.processors.JSONRenderer()
        ]
    )

def get_logger(module: str):
    """获取模块级 Logger"""
    return structlog.get_logger(module=module)
```

### 5.2 日志文件清单

| 文件 | 内容 | 写入时机 |
|:---|:---|:---|
| `data/logs/event_log.jsonl` | 系统里程碑事件 | 关键阶段开始/结束/失败 |
| `data/logs/trade_log.jsonl` | 成交记录 | 每笔 Fill |
| `data/logs/order_log.jsonl` | 订单意图与拒单 | 每笔 Order |
| `data/logs/decision_log.jsonl` | LLM 决策全量 | 每分钟 Decision |
| `data/logs/scheduler_log.jsonl` | 调度状态 | 每 Tick |
| `data/logs/risk_log.jsonl` | 风控事件 | 状态变更/拒单 |
| `data/logs/memory_log.jsonl` | Memory 操作 | 写入/检索/压缩 |
| `data/logs/reflection_log.jsonl` | 复盘记录 | 日终 |
| `data/logs/market_log.jsonl` | 行情异常 | 缺失/陈旧 |
| `data/logs/error.log` | 未分类错误 | 异常 |

### 5.3 Event Log 格式

```json
{
  "timestamp": "2026-07-28T09:31:02.345+08:00",
  "event": "RISK_REJECTED",
  "tick_id": "tick_20260728_093100",
  "date": "2026-07-28",
  "latency_ms": 12,
  "status": "OK",
  "detail": {
    "code": "600584",
    "action": "BUY",
    "reason": "REASON_LOW_CONFIDENCE",
    "confidence": 0.45,
    "threshold": 0.60
  }
}
```

### 5.4 Event 类型枚举（统一事件定义）

所有模块间通信优先通过事件解耦，避免模块直接调用。Replay 监听所有事件。

```python
class SystemEvent(Enum):
    # === 调度与生命周期 ===
    SCHEDULER_DAY_START = "SCHEDULER_DAY_START"
    TRADING_SESSION_START = "TRADING_SESSION_START"
    SESSION_SUSPEND = "SESSION_SUSPEND"
    DAY_CLOSE_FINISHED = "DAY_CLOSE_FINISHED"

    # === 行情与 Feature ===
    MARKET_UPDATED = "MARKET_UPDATED"
    FEATURE_UPDATED = "FEATURE_UPDATED"
    SKIP_STALE = "SKIP_STALE"

    # === 决策链路 ===
    CONTEXT_ASSEMBLED = "CONTEXT_ASSEMBLED"
    CONTEXT_FALLBACK = "CONTEXT_FALLBACK"
    DECISION_FINISHED = "DECISION_FINISHED"
    LLM_TIMEOUT = "LLM_TIMEOUT"

    # === 风控 ===
    RISK_PASSED = "RISK_PASSED"
    RISK_REJECTED = "RISK_REJECTED"
    STOP_LOSS_TRIGGERED = "STOP_LOSS_TRIGGERED"
    HALT_TRIGGERED = "HALT_TRIGGERED"
    LIQUIDATE_TRIGGERED = "LIQUIDATE_TRIGGERED"

    # === 交易执行 ===
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    EXECUTION_FINISHED = "EXECUTION_FINISHED"

    # === Tick ===
    TICK_STARTED = "TICK_STARTED"
    TICK_FINISHED = "TICK_FINISHED"

    # === 记忆与复盘 ===
    MEMORY_WRITTEN = "MEMORY_WRITTEN"
    MEMORY_UPDATE_FINISHED = "MEMORY_UPDATE_FINISHED"
    REFLECTION_STATS_READY = "REFLECTION_STATS_READY"
    REFLECTION_FINISHED = "REFLECTION_FINISHED"

    # === 计划与理解（第二阶段） ===
    MARKET_UNDERSTANDING_FINISHED = "MARKET_UNDERSTANDING_FINISHED"
    PLANNER_FINISHED = "PLANNER_FINISHED"

    # === Replay ===
    REPLAY_PACKAGE_SAVED = "REPLAY_PACKAGE_SAVED"

    # === 系统 ===
    WATCHDOG_RESTART = "WATCHDOG_RESTART"
    CONFIG_LOADED = "CONFIG_LOADED"
```

**事件解耦原则：**

| 规则 | 说明 |
|:---|:---|
| Replay 监听所有事件 | Replay Store 订阅全部事件流，不遗漏 |
| 事件不可篡改 | 事件发出后不可修改，只可追加 |
| 模块间低耦合 | 模块通过事件通知而非直接调用（调度链路除外） |
| 事件必须包含 tick_id | 交易时段内事件必须关联 Tick |

### 5.5 日志轮转与保留

- JSONL 文件按日轮转：`trade_log.20260728.jsonl`
- 保留策略：最近 90 日在线，更早压缩归档
- Event Log 保留 180 日（审计需要）

---

## 6. 测试策略

### 6.1 测试层次

| 层次 | 覆盖范围 | 工具 | 目标覆盖率 |
|:---|:---|:---|:---|
| 单元测试 | 费用计算、T+1、状态机、止损、置信度过滤 | pytest | 核心逻辑 >95% |
| 集成测试 | Tick 完整流程、日级生命周期、Replay 回放 | pytest + fixture | 关键路径 100% |
| 验收测试 | PRD 15 条核心验收标准 | pytest（参数化） | 100% 通过 |
| 回归测试 | 每次提交自动运行 | CI (GitHub Actions) | 不引入回归 |

### 6.2 关键测试用例（对应验收标准）

```python
# === tests/acceptance/test_acceptance_01.py ===

class TestAcceptance01RiskAtomicity:
    """验收1：风控原子性"""
    def test_halt_blocks_buy_same_tick(self):
        """Tick 内触发 HALT 后，本分钟无 BUY 成交"""
        ...

class TestAcceptance02DeepStopLoss:
    """验收2：止损深度穿透"""
    def test_no_bid1_mark_price_deep_breach(self):
        """无 bid1，mark_price 击穿 stop_loss*0.98，立即止损"""
        ...

class TestAcceptance03LiquidationCrossDay:
    """验收3：清仓跨日累计"""
    def test_30_attempts_across_days(self):
        """连续跌停，attempts 跨日累计至 30 → LIQ_FAIL"""
        ...

class TestAcceptance04FeePrecision:
    """验收4：费用精度"""
    def test_2yuan_100shares_round_trip(self):
        """2元股100股往返 ≈ 10.10 元"""
        fee_calc = FeeCalculator()
        buy = fee_calc.buy_fee(Decimal("200"))   # 5.00
        sell = fee_calc.sell_fee(Decimal("200")) # 5.10
        assert buy + sell == Decimal("10.10")

class TestAcceptance05SessionSuspend:
    """验收5：14:57后不执行"""
    def test_no_execution_after_1457(self):
        ...
```

### 6.3 测试 Fixture 设计

```python
# === tests/conftest.py ===
import pytest

@pytest.fixture
def default_config():
    """标准测试配置"""
    return AppConfig()

@pytest.fixture
def sample_account():
    """标准测试账户（30000元，含2只持仓）"""
    ...

@pytest.fixture
def mock_quotes():
    """模拟行情数据"""
    return {
        "600584": Quote(code="600584", last=28.0, bid1=27.9, ask1=28.1,
                        high=28.5, low=27.5, open=27.8, pre_close=27.6,
                        limit_up=30.36, limit_down=24.84,
                        volume=1000000, is_suspended=False),
    }

@pytest.fixture
def mock_llm_client():
    """Mock LLM 客户端（返回预设 JSON）"""
    ...
```

### 6.4 测试数据管理

- 使用 `tests/fixtures/` 存放 JSON 测试数据
- 行情数据：手动构造 + 历史真实数据采样
- 不依赖外部网络（tushare/akshare 在测试中 Mock）

---

## 7. 部署方案

### 7.1 系统要求

| 项目 | 要求 |
|:---|:---|
| OS | Ubuntu 22.04 LTS / 24.04 LTS |
| Python | 3.11+ |
| 内存 | >= 2GB |
| 磁盘 | >= 20GB（日志/Replay 增长） |
| 网络 | 可访问 LLM API + 行情数据源 |
| 时间同步 | NTP（chrony） |

### 7.2 依赖清单

```
# requirements.txt
pandas>=2.0
akshare>=1.10
tushare>=1.4
pydantic>=2.0
structlog>=23.0
pyyaml>=6.0
schedule>=1.2
openai>=1.0
httpx>=0.24
python-dotenv>=1.0
```

### 7.3 systemd 服务配置

```ini
# deploy/ai-t-agent.service
[Unit]
Description=AI-T-Agent Main Process
After=network.target chronyd.service
Wants=network-online.target

[Service]
Type=simple
User=aitagent
Group=aitagent
WorkingDirectory=/opt/ai-t-agent
Environment=PYTHONPATH=/opt/ai-t-agent/src
EnvironmentFile=/opt/ai-t-agent/.env
ExecStart=/opt/ai-t-agent/.venv/bin/python -m agent.main
Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=300
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/ai-t-agent/data

[Install]
WantedBy=multi-user.target
```

```ini
# deploy/ai-t-agent-watchdog.service
[Unit]
Description=AI-T-Agent WatchDog
After=ai-t-agent.service
BindsTo=ai-t-agent.service

[Service]
Type=simple
User=aitagent
WorkingDirectory=/opt/ai-t-agent
ExecStart=/opt/ai-t-agent/.venv/bin/python -m agent.watchdog.watchdog
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 7.4 WatchDog 策略

| 监控项 | 检测方式 | 恢复动作 |
|:---|:---|:---|
| 主进程存活 | systemd + 心跳文件（每 30s 更新） | 重启主进程 |
| LLM 连续超时 | 计数 > 5 次/日 | 切换降级模式（跳过 LLM，仅维护风控+清仓） |
| 行情中断 | 连续 3 分钟无新数据 | 告警 + 暂停决策 |
| 磁盘空间 | < 1GB | 告警 + 清理旧日志 |
| 账户一致性 | 日终校验 NAV = cash + positions | 告警 + 阻断次日开盘 |

### 7.5 备份策略

- 每日 15:30 cron 执行备份脚本
- 备份内容：Account 快照、Memory DB、Config、当日 Replay 包
- 保留最近 30 日备份，更早的压缩归档

### 7.6 恢复流程

```
进程崩溃 → systemd 自动重启（10s 延迟）
         → 加载 data/account/state.json（最近落盘）
         → 校验完整性
         → 恢复 Scheduler 主循环
         → 不重放未确认成交
```

---

## 8. 模块间调用关系（第一阶段）

```
┌─────────────────────────────────────────────────────────────┐
│                      Scheduler                               │
│  (驱动 Tick 循环 / 日切 / 日终)                              │
└─────────────┬───────────────────────────────────────────────┘
              │ 每分钟触发
              ▼
┌─────────────────────────┐
│      TickExecutor        │
│  (原子执行顺序控制)       │
└──┬──────┬──────┬──────┬─┘
   │      │      │      │
   │      │      │      └──────────────────────┐
   ▼      ▼      ▼                             ▼
┌──────┐┌──────┐┌──────────┐           ┌────────────┐
│Risk  ││Trading││ Decision │           │ Reflection │
│Engine││Engine││ Engine   │           │ (日终)     │
└──┬───┘└──┬───┘└────┬─────┘           └─────┬──────┘
   │       │         │                       │
   │       │         ▼                       ▼
   │       │   ┌───────────┐           ┌──────────┐
   │       │   │  Context   │           │  Memory  │
   │       │   │ Assembler  │◄──────────│  Writer  │
   │       │   └─────┬─────┘           └──────────┘
   │       │         │                       ▲
   │       │         ▼                       │
   │       │   ┌───────────┐           ┌─────┴────┐
   │       │   │  Memory    │           │Replay    │
   │       │   │ Retriever  │           │Store     │
   │       │   └───────────┘           └──────────┘
   │       │
   ▼       ▼
┌─────────────────┐
│  Account / Fee  │
│  Position/Order │
│  Liquidation    │
│  Benchmark      │
└─────────────────┘
```

**调用方向约束（不可违反）：**

| 规则 | 说明 |
|:---|:---|
| Decision 不可直接调用 Trading Engine | 必须经 Risk Engine |
| Risk Engine 不可调用 LLM | 纯代码规则 |
| Trading Engine 不可修改 Risk State | 只读 |
| Scheduler 是唯一循环驱动者 | 其他模块被动响应 |
| WatchDog 不可修改账户 | 只能重启/告警 |

---

## 9. 开发里程碑与验收检查点

| 里程碑 | 模块 | 完成标志 | 预计周期 |
|:---|:---|:---|:---|
| M1 | Trading Engine + Fee | 费用精度测试通过；T+1 测试通过；状态机测试通过 | 2 周 |
| M2 | Risk Engine | 三级风控状态机测试通过；止损/置信度过滤测试通过 | 1.5 周 |
| M3 | Scheduler + 集成 | 完整 Tick 流程可跑通；14:57 挂起正确 | 1.5 周 |
| M4 | Replay | 同包回放一致；Decision 引用信息完整 | 1 周 |
| M5 | Memory | 跨日重启可用；检索注入正确 | 1 周 |
| M6 | Decision + Context | LLM 决策链路跑通；Schema 校验正确 | 1.5 周 |
| M7 | Reflection + 日报 | 统计与账本一致；日报输出完整 | 1 周 |
| M8 | 全量验收 | 15 条验收标准全部通过；连续 5 日无人值守运行 | 1 周 |

**总计约 10-11 周（单人开发）**

---

## 10. 关键设计决策记录

| 决策 | 选择 | 理由 |
|:---|:---|:---|
| 金额精度 | `Decimal` | 避免浮点误差，费用计算必须精确 |
| 持久化 | JSON 文件 + SQLite | MVP 简单可靠；无需部署数据库服务 |
| 调度方式 | `schedule` + 自实现 Tick 循环 | 比 APScheduler 轻量；满足分钟级需求 |
| LLM 输出解析 | JSON Schema 校验 + 1 次重试 | 平衡可靠性与延迟 |
| 配置格式 | YAML + Pydantic | 可读性好；强类型校验 |
| 日志格式 | JSONL (structlog) | 结构化、可 grep、可 Replay |
| 单飞行 | 简单布尔锁 | 单线程 Tick 内无需复杂并发控制 |
| 基准重建 | 清空重建（非增量） | PRD 明确要求；避免增量计算偏差累积 |

---

## 11. 风险与注意事项

| 风险 | 影响 | 缓解措施 |
|:---|:---|:---|
| LLM 输出不稳定 | 决策质量波动 | Schema 强校验 + confidence 过滤 + 重试 |
| 行情数据源不稳定 | 无法决策 | 陈旧检测 + 降级 HOLD + 多源备选 |
| 费用计算精度 | 验收不通过 | 全链路 Decimal + 专项测试 |
| 清仓跨日状态丢失 | 计数清零 | attempts 持久化至 Account JSON |
| 磁盘写满 | 系统崩溃 | WatchDog 监控 + 日志轮转 + 备份清理 |
| 时区/时钟问题 | Tick 错乱 | 强制 Asia/Shanghai + NTP 同步 |

---

## 12. 统一错误码（Error Code）

所有模块统一返回 Error Code，方便日志、测试、排查。

实现位置：`src/agent/common/errors.py`

### 错误码定义

```python
class ErrorCode(Enum):
    # === 通用 ===
    E001 = "SCHEMA_VALIDATION_FAILED"      # Schema 校验失败
    E002 = "LLM_TIMEOUT"                   # LLM 调用超时
    E003 = "RISK_REJECT"                   # 风控拒绝
    E004 = "REPLAY_FAILED"                 # Replay 回放失败
    E005 = "QUOTE_TIMEOUT"                 # 行情超时/缺失
    E006 = "MEMORY_RETRIEVE_FAILED"        # Memory 检索失败
    E007 = "CONFIG_LOAD_FAILED"            # 配置加载失败
    E008 = "ACCOUNT_PERSIST_FAILED"        # 账户持久化失败
    E009 = "CONTEXT_ASSEMBLE_FAILED"       # Context 组装失败
    E010 = "EVENT_EMIT_FAILED"             # 事件发出失败

    # === 交易 ===
    E101 = "MATCH_FAILED"                  # 撮合失败
    E102 = "FEE_CALC_ERROR"                # 费用计算异常
    E103 = "LIQUIDATION_EXHAUSTED"         # 清仓重试耗尽
    E104 = "POSITION_STATE_INVALID"        # 持仓状态非法
    E105 = "BENCHMARK_REBUILD_FAILED"      # 基准重建失败

    # === 风控 ===
    E201 = "HALT_TRIGGERED"                # HALT 触发
    E202 = "LIQUIDATE_TRIGGERED"           # LIQUIDATE 触发
    E203 = "STOP_LOSS_TRIGGERED"           # 止损触发
    E204 = "CONFIDENCE_TOO_LOW"            # 置信度过低
    E205 = "CASH_RESERVE_BREACH"           # 现金预留突破
    E206 = "POSITION_LIMIT_BREACH"         # 单票上限突破

    # === 调度 ===
    E301 = "TICK_TIMEOUT"                  # Tick 执行超时
    E302 = "SCHEDULER_CRASH"               # 调度器崩溃
    E303 = "CALENDAR_ERROR"                # 交易日历错误
    E304 = "WATCHDOG_RESTART"              # WatchDog 重启

    # === 记忆 ===
    E401 = "MEMORY_WRITE_FAILED"           # Memory 写入失败
    E402 = "MEMORY_COMPRESS_FAILED"        # Memory 压缩失败
    E403 = "MEMORY_STORE_CORRUPT"          # Memory 存储损坏

    # === 复盘 ===
    E501 = "STATS_MISMATCH"                # 统计与账本不一致
    E502 = "REFLECTION_LLM_FAILED"         # 复盘 LLM 失败
    E503 = "REPORT_GENERATE_FAILED"        # 日报生成失败
```

### 错误码使用规则

| 规则 | 说明 |
|:---|:---|
| 所有异常必须携带 ErrorCode | 禁止裸抛异常，必须包含错误码 |
| 日志必须记录 ErrorCode | 方便 grep 与统计 |
| 测试可按 ErrorCode 断言 | 验收用例可精确匹配错误类型 |
| 错误码不可复用 | 一个码对应一种错误，禁止一码多用 |
| 扩展规则 | 新增错误码按模块段递增（通用 0xx、交易 1xx、风控 2xx、调度 3xx、记忆 4xx、复盘 5xx） |

### 统一异常类

```python
@dataclass
class AgentError(Exception):
    """统一异常基类"""
    code: ErrorCode
    message: str
    module: str
    tick_id: Optional[str] = None
    detail: Optional[dict] = None

    def __str__(self):
        return f"[{self.code.name}] {self.module}: {self.message}"
```

---

## 13. Schema 版本注册表（Schema Version Registry）

所有持久化 Schema 必须携带版本号，升级时向后兼容优先，破坏性变更必须升主版本。

### 注册表

| Schema | 当前版本 | 说明 | 升级规则 |
|:---|:---|:---|:---|
| `account.v1` | v1 | Account 持久化结构 | 新增字段向后兼容；删除/改名升主版本 |
| `feature.v1` | v1 | 基础市场/账户 Feature 字段集 | 新增 Feature 字段不升版；删除/改名升版 |
| `memory.v1` | v1 | Memory 条目结构 | 新增字段可选；结构变更升版 |
| `prompt.v1` | v1 | Prompt 元数据与渲染契约 | 模板内容变更走 prompt_version；结构变更升 schema |
| `context.v1` | v1 | 统一 Context 结构 | 新增切片向后兼容；删除升版 |
| `decision.v1` | v1 | Decision JSON（含 confidence 等） | 新增字段可选；删除/改名升版 |
| `replay.v1` | v1 | Replay 包结构 | 新增字段向后兼容；结构重构升版 |
| `reflection.v1` | v1 | Reflection 统计+分析结构 | 新增统计字段不升版；结构变更升版 |

### 版本管理规则

| 规则 | 说明 |
|:---|:---|
| 向后兼容优先 | 新增字段设为可选（Optional），旧数据仍可读取 |
| 破坏性变更升主版本 | 删除字段、改名、改类型 → v1 → v2 |
| 双读策略 | 升版后提供迁移脚本，支持同时读取 v1/v2 |
| Replay 记录版本 | 每个 Replay 包记录当时使用的所有 Schema 版本 |
| 禁止无版本数据 | 任何持久化数据必须携带 schema_version，缺失视为非法 |

### 版本记录实现

```python
# === common/schema_registry.py ===
SCHEMA_VERSIONS = {
    "account": "account.v1",
    "feature": "feature.v1",
    "memory": "memory.v1",
    "prompt": "prompt.v1",
    "context": "context.v1",
    "decision": "decision.v1",
    "replay": "replay.v1",
    "reflection": "reflection.v1",
}

def get_schema_version(schema_name: str) -> str:
    """获取当前 Schema 版本"""
    return SCHEMA_VERSIONS[schema_name]

def validate_schema_version(data: dict, schema_name: str) -> bool:
    """校验数据携带的 schema_version 是否合法"""
    expected = SCHEMA_VERSIONS[schema_name]
    return data.get("schema_version") == expected
```

---

## 14. 统一模块接口规范（Interface Standard）

所有可独立开发的模块必须采用统一接口模板，保证风格一致、方便多人协作与 AI 辅助开发。

### 模块模板字段

| 字段 | 含义 | 必须 |
|:---|:---|:---|
| **Purpose** | 模块解决什么问题 | ✓ |
| **Input** | 输入是什么（类型 + 来源） | ✓ |
| **Output** | 输出是什么（类型 + 消费者） | ✓ |
| **Dependencies** | 依赖哪些模块 | ✓ |
| **Processing** | 处理流程（含核心类设计） | ✓ |
| **Validation** | 输入输出校验规则 | ✓ |
| **Failure Handling** | 失败如何处理 | ✓ |
| **Logging** | 记什么日志 | ✓ |
| **Replay** | 如何回放/审计 | ✓ |
| **Future Extension** | 未来可扩展方向（仅记录，不实现） | 可选 |

### 与 PRD 字段映射

| PRD 既有字段 | 模块模板字段 |
|:---|:---|
| Objective | Purpose |
| Scope / Architecture | Dependencies |
| Workflow | Processing |
| Data Structure | Input / Output |
| Exception Handling | Failure Handling |
| Logging | Logging |
| Acceptance / Replay 要求 | Replay |
| — | Validation（新增） |
| — | Future Extension（新增） |

### 使用说明

- 本 SPEC 第 2 章各模块已按此模板书写（包含 Purpose/Input/Output/Dependencies/Processing/Failure Handling/Logging/Replay）
- 后续新增模块实现文档一律按此模板拆分
- `Validation` 字段明确输入输出的校验规则（如 Schema 校验、范围检查、非空约束）
- `Future Extension` 仅记录方向，不在当前版本实现

---

## 15. 文档状态与批准

| 项目 | 状态 |
|:---|:---|
| PRD V2.0 Final | **Frozen** |
| SPEC V1.1 Final | **Frozen — Enter Development** |
| Final Review | **Approved for Development**（评分 9.8/10） |
| 下一步 | 建立 Git 仓库，进入 Implementation Phase |

**未来所有升级均采用 Version Iteration，不修改基础架构。**

**所有后续优化应来自：真实模拟盘运行、Replay 数据、日志分析、测试结果。**

---

*文档结束 — 基于 PRD V2.0 Final，开发规格说明书 V1.1 Final（Frozen）*
