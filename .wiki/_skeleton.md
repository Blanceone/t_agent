---
type: "内部"
title: "Wiki 骨架（构建计划）"
description: "本仓库 OpenWiki 初始化阶段的骨架规划：目标目录结构、每页职责与覆盖范围、证据来源、未知未知项检查清单。"
tags: [skeleton, planning]
---

# Wiki 骨架（构建计划）

本文件是初始化工作流的骨架规划（`/openwiki/_skeleton.md`），描述将要生成的所有 wiki 页面及其内容范围。页面正文将在骨架评审通过后逐一撰写。本文件在全部页面完成后删除。

## 仓库概况

仓库根（虚拟根 `/`）。核心项目是 `ai-t-agent/`（Python 3.11+，pyproject.toml），一个「Rule + LLM」架构的 A 股日内做 T 个人量化交易 Agent（模拟盘）。其余内容：

- `docs/`：`PRD_Personal_AI_Quant_Trading_Agent.md`（V2.0 Final，13 章 + 工程规范 + 15 项验收标准）与 `SPEC_Development.md`（V1.1 Final，模块级 SPEC），是设计意图来源，代码为准。
- `tmp_logs/`：生产服务器运行样例（`event_log.jsonl` 3043 行、`agent.log` 1100 行、`state.json`、两份 `*_daily.json`），是存储布局与日循环的真实证据。
- `conversation_history/`：空目录，无内容。
- `skills/`：OpenWiki 技能库（mermaid-diagrams、write-connector），非仓库业务代码，不在 wiki 范围。
- `/.wiki/`：旧运行留下的重复骨架目录，非本仓库业务，不写入。

## 覆盖范围判定（rank）

| 排名 | 系统 | 理由 | 覆盖 |
|:--|:--|:--|:--|
| 1 | `src/agent/trading/` | 账本唯一真相源，dependency centrality 最高 | 独立目录 6 页 |
| 2 | `src/agent/risk/` | 决策必经风控，三级状态机是核心不变量 | 独立目录 3 页 |
| 3 | `src/agent/scheduler/` | 唯一调度中心，驱动日级与分钟级生命周期 | 独立目录 3 页 |
| 4 | `src/agent/decision/` + `llm/` | LLM 决策链路（Prompt→LLM→Validator） | 独立目录 5 页 |
| 5 | `src/agent/market/` | 行情接入与 Regime 判定 | 独立目录 2 页 |
| 6 | `src/agent/memory/` | 长期记忆（SQLite+JSONL 双写） | 独立目录 2 页 |
| 7 | `src/agent/reflection/` + `replay/` | 日终复盘与回放评估 | 独立目录各 1 页 |
| 8 | `src/agent/common/` + `config/` | 领域模型/错误码/事件/日志/配置 | 2 页 |
| 9 | `scripts/`、`deploy/`、`watchdog/` | 运维与扩展面 | operations 目录 3 页 |
| 10 | `tests/` | 22 单元 + 33 验收测试，覆盖全部核心不变量 | testing 目录 2 页 |

## 目录结构与每页职责

```
/openwiki/
├── quickstart.md                     # 入口：仓库地图、概念导航、变更任务路由表（最后撰写）
├── architecture/
│   ├── overview.md                   # 系统架构总览与设计哲学（Rule+LLM、双层架构、时间轴）
│   ├── data-flow.md                  # 数据/控制/事件三流 + 存储布局 + schema 版本清单
│   └── domain-models.md              # 统一领域模型（models.py 全量枚举与 dataclass）
├── configuration.md                  # 配置系统（schema.py + loader.py + default.yaml + .env）
├── common-infrastructure.md          # 错误码/EventLog/结构化日志/工具函数
├── trading/                          # 交易引擎（src/agent/trading/）
│   ├── overview.md                   # TradingEngine 装配、execute_order 链路、日切/日终
│   ├── account.md                    # Account/Cash/NAV 口径/原子持久化（account.v1）
│   ├── matching-fees.md              # SimMatcher + FeeCalculator（含验收4 公式）
│   ├── positions-t1.md               # PositionManager 状态机与 T+1、加权成本
│   ├── liquidation.md                # LiquidationWorker 清仓队列（30 次跨日累计）
│   └── benchmark-settlement.md       # BenchmarkManager + SettlementManager
├── risk/                             # 风控引擎（src/agent/risk/）
│   ├── overview.md                   # RiskEngine 校验流水线（顺序不可变）
│   ├── state-machine.md              # RiskStateManager 三级状态机公式与恢复规则
│   └── detectors.md                  # StopLossDetector + ConfidenceFilter + PositionLimitChecker
├── decision/                         # 决策链路（src/agent/decision/ + llm/）
│   ├── overview.md                   # DecisionEngine.decide 六步流程与 Prompt 构建
│   ├── context.md                    # ContextAssembler（已实现但未接入运行时——重点差异）
│   ├── planner.md                    # Planner + REGIME_CONSTRAINTS + TodayPlan
│   ├── validator.md                  # DecisionValidator schema 校验规则
│   └── llm-client.md                 # LLMClient + SingleFlightGuard + last_error 状态机
├── market/                           # 行情与市场理解（src/agent/market/）
│   ├── service.md                    # MarketService 三源回退链 + FeatureEngine（未接入运行时）
│   └── understanding.md              # RegimeDetector + MarketUnderstandingEngine
├── memory/                           # 记忆系统（src/agent/memory/）
│   ├── store.md                      # MemoryStore/Writer/Retriever（SQLite 表结构、seq 恢复）
│   └── compression.md                # MemoryCompressor（已实现但未接入日终流程——重点差异）
├── scheduler/                        # 调度中心（src/agent/scheduler/）
│   ├── lifecycle.md                  # Scheduler 日级生命周期与 _dispatch 分发
│   ├── tick-execution.md             # TickExecutor 九步原子流程
│   └── calendar.md                   # TradingCalendar + scripts/init_calendar.py
├── reflection/                       # 日终复盘（src/agent/reflection/）
│   └── overview.md                   # ReflectionEngine + ReflectionStats + ReportGenerator
├── replay/                           # 回放（src/agent/replay/）
│   └── overview.md                   # ReplayStore（未接入 Tick）+ ReplayRunner + Evaluator
├── operations/
│   ├── cli.md                        # scripts/cli.py 七条指令 + 其他脚本 + manage.ps1/agent.sh
│   ├── deployment.md                 # deploy/ 部署、systemd、备份
│   └── watchdog.md                   # WatchDog（heartbeat 无写入方——差异点）
├── testing/
│   ├── overview.md                   # 测试策略、运行方式、fixture、分层
│   └── acceptance-criteria.md        # 15 项验收标准 → 代码/测试映射
└── references/
    └── design-docs.md                # PRD/SPEC 导航、设计原则、文档与代码的差异
```

## 每页内容要点与证据锚点

### architecture/overview.md
- Rule + LLM 分工、代码为体/模型为脑/记忆为魂/Replay 负责成长（README.md「核心原则」、docs/PRD Chapter 0）
- 组合根：`src/agent/main.py`（load_config → 各引擎装配 → Scheduler.run；KeyboardInterrupt 时 persist）
- 双层架构：确定性层（trading/risk/scheduler/memory/replay/reflection stats）与 LLM 层（decision、market understanding、planner、reflection 归因）
- 一天时间轴（README 交易时间轴 + PRD Chapter 9）：09:20 日切 → 09:30-11:30/13:00-14:56 每分钟 Tick → 14:57 挂起 → 15:05 日终
- 已实现但未接入运行时的模块清单（本页与 data-flow 页列出）：
  - `ContextAssembler`（仅测试使用）
  - `FeatureEngine`（main.py 导入但未实例化）
  - `ReplayStore.save_tick`（Replay 录制未接入 Tick）
  - `MemoryCompressor.run_daily`（无调用方）
  - `WatchDog.update_heartbeat`（无写入方）
- Mermaid：模块关系流程图

### architecture/data-flow.md
- 数据流：`MarketService.refresh → Quote → AccountSnapshot → DecisionEngine(Prompt) → LLM → DecisionOutput → RiskEngine.validate_decision → TradingEngine.execute_order → Fill → Account`
- 控制流：`Scheduler._dispatch → TickExecutor.execute`（严格顺序九步，全同步）
- 事件流：EventLog（`common/event_log.py`，`SystemEvent` 全量枚举在 models.py:85-136）
- 存储布局（data/ 目录 + tmp_logs/ 真实样例）：
  - `data/account/state.json`（account.v1，tmp_logs/state.json 实证：schema_version/positions/watchlist/benchmark 字段）
  - `data/memory/memory.db` + `items.jsonl`
  - `data/replay/<date>/ticks.jsonl` + `daily_summary.json`
  - `data/logs/event_log.jsonl` + `agent.log`
  - `data/reports/<date>_daily.json`（reflection.v1，tmp_logs/2026-08-06_daily.json 实证）
  - `data/snapshots/`（backup.sh 每日备份）
- schema 版本清单：account.v1 / context.v1 / decision.v1 / feature.v1 / memory.v1 / replay.v1 / reflection.v1

### architecture/domain-models.md
- 枚举：RiskState、PositionState、ActionType、OrderSource、MemoryType、MarketRegime、RejectReason（含未使用的 INTRADAY_BUY_LIMIT/LOSS_LINK_REJECT）、SystemEvent（models.py:18-137）
- 核心 dataclass：Quote（mark_price 回退链）、FeatureSnapshot、Position、Cash、AccountSnapshot、OrderIntent、Fill、LiquidationTask、DecisionItem/DecisionOutput、RiskVerdict/RiskSnapshot、MemoryItem、TickRecord、EqualWeightBenchmark/CSI300Benchmark/BenchmarkPortfolio（models.py 全量）
- 约束：模块 docstring「只能使用本文件定义的模型，禁止裸 dict 传业务数据」

### configuration.md
- 加载顺序：`.env`（load_dotenv）→ `default.yaml` → `config/{env}.yaml`（不存在则跳过）→ `merged["env"]=env` → `AppConfig(**merged)`（loader.py:21-67，`_deep_merge` 递归合并）
- AppConfig 全量参数（schema.py）：FeeConfig/RiskConfig/TradingConfig/SchedulerConfig/LLMConfig/PromptConfig/MemoryConfig/MarketConfig/FeatureConfig/DecisionConfig/ReplayConfig/ReflectionConfig + log_level/data_dir
- default.yaml 实测值：费率、止损/HALT/LIQUIDATE 阈值、调度时间、LLM provider=zhipu/model=glm-4-flash
- .env 密钥约定（.env.example）：LLM_API_KEY、LLM_BASE_URL、TUSHARE_TOKEN、ENV
- 关键点：api_key/base_url 在 LLMClient 中用环境变量名间接读取；tushare token 同

### common-infrastructure.md
- ErrorCode 分段（0xx 通用/1xx 交易/2xx 风控/3xx 调度/4xx 记忆/5xx 复盘）+ AgentError 家族（errors.py：SchemaValidationError/LLMTimeoutError/QuoteTimeoutError/AccountPersistError/MatchFailedError/LiquidationExhaustedError）
- EventLog：`data/logs/event_log.jsonl` JSONL 记录结构（timestamp/event/tick_id/date/latency_ms/status/detail），`emit` 与 `emit_with_timer`（异常自动记 FAILED）
- structlog：setup_logging（JSONRenderer 文件 / ConsoleRenderer 控制台）、bind_tick_context/bind_decision_context/clear_context（logger.py）
- utils.py：now_cst/today_str、gen_tick_id/gen_id 系列、gen_memory_id、gen_context_id、compute_hash(SHA256 前16)、decimal_round、pct_change

### trading/overview.md
- TradingEngine 子模块装配（engine.py:50-74）与 execute_order 链路（matcher.match → _apply_fill → 清仓完成处理）
- is_liquidation 来源（LIQUIDATE/STOP_LOSS/USER_REMOVE）与 _on_position_cleared 三分支（移出池/留池冷却/仅清仓）
- enqueue_liquidation（用 total_shares，T+1 解冻后自然可卖）/ process_liquidation（耗尽→LIQ_FAIL）
- on_day_start（结算→reset_daily→nav_open 记录→watchlist 变更时基准重建）/ on_day_end（update_nav→基准重估→save）
- 与 RiskEngine 的关系：engine.py docstring「所有交易必须经 Risk Engine 校验」
- Mermaid：订单执行序列图

### trading/account.md
- NAV 口径：nav_mark = cash.available + Σ(mark_price×total_shares)（account.py:71-80）
- snapshot() 不可变快照；watchlist 管理（add/remove + WatchlistEntry cooldown_until_date）；reset_daily；update_nav（peak_nav 更新）
- 持久化：save() 用 tempfile + os.replace 原子写入（account.py:133-156）；load() 反序列化含 benchmark
- 真实数据样例：tmp_logs/state.json（10000 初始资金、002185/600584 池、等权基准 10332.47）
- 注意：CLI `cmd_set_cash` 直接改 cash/initial/last/peak，未实现 PRD 8.2 的校验（amount >= market_value + nav*10%）

### trading/matching-fees.md
- FeeCalculator：印花税 0.05% 卖出、过户费 0.001% 双边、佣金万 2.5 最低 5 元；ROUND_HALF_UP 2 位小数；round_trip_fee_est 公式（fee.py:65-83，PRD 5.2 C）
- SimMatcher 零滑点：BUY 按 ask1、SELL 按 bid1；停牌/涨停/跌停/无盘口/100 股整数倍/可卖不足/非清仓零股拒单（matcher.py:111-179）；realized_pnl=(price-cost)×shares-fee
- RejectReason 映射表
- 测试：tests/unit/test_fee.py（验收4：2 元股 100 股往返 = 10.10）

### trading/positions-t1.md
- PositionManager 状态机：ACTIVE → CLEARING →（清零后处理 / LIQ_FAIL）（position.py）
- T+1：建仓 sellable=0、加仓不增可卖、日切解冻（sellable=total, today_bought=0, breach 清零）
- 加权平均成本公式与 4 位小数精度（_round_price 0.0001）
- can_buy（仅 ACTIVE）/ can_sell（ACTIVE+CLEARING）
- 测试：tests/unit/test_t1.py（验收1/2）

### trading/liquidation.md
- LiquidationWorker：每分钟拆单 min(remaining, max_shares_per_tick)、清仓允许零股（is_liquidation=True）、attempts 跨日累计不清零、≥30 次 → exhausted → LIQ_FAIL（liquidation.py:41-131）
- remove_completed 过滤规则
- 测试：tests/acceptance/test_acceptance_01.py TestAcceptance03LiquidationCrossDay

### trading/benchmark-settlement.md
- BenchmarkManager：等权组合按 pre_close 全仓等权分配、watchlist 变更时清空重建（benchmark.py:31-66）、日终 update_equal_weight 重估；CSI300 净值按收盘价比例更新（update_csi300，暂无调用方）
- SettlementManager：日切 T+1 解冻 + stop_breach_count 清零 + 冷却清理（settlement.py:29-52）；is_in_cooldown
- 测试：tests/acceptance/test_acceptance_02.py TestAcceptance06BenchmarkRebuild

### risk/overview.md
- RiskEngine 校验流水线（engine.py:118-183）：LIQUIDATE→HALT 禁 BUY→置信度→(BUY: 状态→冷却→现金预留→单票上限)→(SELL: 可卖)→PASS，顺序不可变
- tick_guard 优先级最高（每分钟扫描）：评估状态 + 止损扫描，返回 TickGuardResult
- 风控强制单（STOP_LOSS/LIQUIDATE）豁免置信度过滤
- 测试：TestAcceptance01RiskAtomicity、TestAcceptance09LLMMustPassRisk
- Mermaid：校验流水线流程图

### risk/state-machine.md
- RiskStateManager：LIQUIDATE（回撤≥10%）> HALT（日亏≥3% 或已实现亏损≤-500）> NORMAL；HALT 不自动恢复；on_day_start 仅 HALT→NORMAL；on_resume（state.py:47-116）
- halt_count_today 计数与 get_day_loss_ratio/get_drawdown_ratio

### risk/detectors.md
- StopLossDetector：触发价 bid1→mark_price、未击穿归零、深度穿透开关（bid1≤stop×0.98 立即）、常规连续 2 分钟（stop_loss.py:43-90）
- ConfidenceFilter：threshold 0.60、HOLD 与 STOP_LOSS/LIQUIDATE 来源豁免、缺失 confidence 视为 0（confidence_filter.py）
- PositionLimitChecker：现金预留（可用-(预买+估费)≥nav×20%，估费=5 最低佣金）、单票上限（mark×(现+新)≤nav×50%）、冷却期（position_limit.py）
- 注意：docstring 提到「换仓亏损联动拒绝」但无实现；enforce_intraday_buy_limit 配置存在但 RiskEngine 未执行

### decision/overview.md
- DecisionEngine.decide 六步：单飞行→构建 Prompt→LLM→Validator 校验→失败重试 1 次（content_filter 不重试）→仍失败 HOLD（engine.py:45-90）
- _build_prompt：风控状态中文中性化、持仓/股票池行情（可买上限=min(现金约束,仓位上限)//100*100）、Today Plan 注入、购买力计算与风控规则一致（engine.py:92-200）
- set_daily_context 注入（Scheduler 日切/日终调用）
- 相关验收：验收13（Context 统一注入——注意实际 Prompt 是 engine 内联构建，ContextAssembler 未接入）

### decision/context.md
- ContextAssembler：System/Market/Portfolio/Holdings/Memory 切片、assemble 截断优先级、context_hash（compute_hash）、render_for_prompt（context.py:95-207）
- schema: context.v1；gen_context_id（ctx_YYYYMMDD_HHMMSS）
- 重点差异：运行时未接入（DecisionEngine 未引用），仅验收测试 11/13 使用——记录为差异而非谎言

### decision/planner.md
- Planner.generate：Regime 约束表 REGIME_CONSTRAINTS（planner.py:50-75）→ LLM 生成（_llm_generate，45s 超时、非法枚举回退默认）→ 失败降级 _default_plan（degraded=True）
- StockPlan/TodayPlan 结构；与 DecisionEngine.set_daily_context 的注入关系
- 输入：mu_output、snapshot、quotes、watchlist、memory_items（Scheduler._on_day_start 传入 memory_retriever 结果）

### decision/validator.md
- DecisionValidator.validate：非法 action→HOLD、confidence 越界→截断/0、BUY 100 整数倍取整、reason 缺省、risk_level 缺省 MEDIUM、referenced_memory 数组化（validator.py:23-110）

### decision/llm-client.md
- LLMClient：OpenAI 兼容、延迟初始化（max_retries=0 快速失败）、call/call_json（```json 块提取）、last_error 状态机（None/content_filter/call_failed，contentFilter/1301 判定）（client.py:36-108）
- SingleFlightGuard：try_acquire/release/in_flight（client.py:16-33）
- LLMConfig：timeout_ms 30000、max_retries 1、temperature 0.1

### market/service.md
- MarketService：set_watchlist/get_quotes/update_quotes（测试注入）/refresh 回退链 tencent→tushare→akshare（service.py:43-68）
- 腾讯接口：qt.gtimg.cn GBK、`_tencent_symbol`（sh/sz/bj 前缀）、字段索引表（名称1/现价3/昨收4/今开5/高33/低34/量36手/额37万/涨停47/跌停48），bid1=ask1=last 简化（service.py:70-137）
- akshare（stock_zh_a_spot_em 全市场过滤）、tushare（get_realtime_quotes 免费接口，无涨跌停价）
- FeatureEngine.compute：open_chg/chg_1d/amplitude/round_trip_fee_est；chg_pct_5d/10d、volume_ratio、turnover_rate 为 None（需历史数据）
- 重点差异：FeatureEngine 在 main.py 导入但未实例化，Feature 未进入运行时

### market/understanding.md
- RegimeDetector：HIGH_VOL（振幅>3% 或量比>2.0）→ LOW_VOL（振幅<1% 且量比<0.7）→ TREND（|涨跌幅|>1.5%）→ RANGE（understanding.py:40-92）
- MarketUnderstandingEngine.run：代码规则候选 → _apply_regime_defaults → LLM 确认/微调（非法回退代码结果）→ 摘要生成；降级 RANGE+MEDIUM（understanding.py:95-289）
- _compute_index_features：用 watchlist 均值近似指数特征（量比恒 1.0——无历史数据）
- MarketUnderstandingOutput 字段与 Regime 默认约束表

### memory/store.md
- MemoryStore：SQLite 表 memory_items（12 列）+ 索引（type/importance）、JSONL 双写、_recover_seq 当日 seq 恢复（防 ID 碰撞）、query 的 codes LIKE 过滤下推 SQL（store.py:20-135）
- MemoryWriter：write_reflection/write_risk_event/write_trade；MemoryRetriever：retrieve_for_decision/retrieve_for_reflection
- 测试：TestAcceptance07MemoryCrossDay

### memory/compression.md
- MemoryCompressor：compress_old（SHORT/TRADE 超 30 天压缩为前 100 字摘要）、promote_important（REFLECTION/HOLDING/PORTFOLIO importance≥0.85 晋升 LONG）、run_daily/get_stats（compressor.py:27-129）
- 重点差异：compressor 无运行时调用方（grep 无引用），属「待接线」能力

### scheduler/lifecycle.md
- Scheduler 主循环：跨日重置（_last_date 变化→_day_started=False）、非交易日 sleep 60、异常捕获不退出（scheduler.py:58-86）
- _dispatch 时间分发：09:20 日切、交易时段内日切补偿、每分钟 Tick、14:57 挂起（_suspend_logged 防刷屏）、15:05 日终（scheduler.py:88-129）
- 日切流程（_on_day_start）：刷新行情→watchlist 变更检测→trading/risk on_day_start→MU→Planner→set_daily_context（scheduler.py:131-186）
- 日终（_on_day_close）：refresh→trading.on_day_end→reflection.run→DAY_CLOSE_FINISHED→清空日级上下文
- PAUSE/RESUME（pause/resume 方法；注意 CLI PAUSE 只写 mode.json，Scheduler 的 _system_mode 需进程内调用——差异点）

### scheduler/tick-execution.md
- TickExecutor.execute 九步（tick.py:46-128）：快照→行情新鲜度（_is_stale 阈值 5s）→RiskGuard（state_changed 时重取快照；止损入队）→LiquidationWorker→LIQUIDATE/PAUSE 短路→LLM Decision→Risk 校验→execute_order→persist+TICK_FINISHED
- SKIP_STALE 语义（无 quotes 或超时）；tick_id 生成与 bind_tick_context
- Mermaid：单 Tick 序列图

### scheduler/calendar.md
- TradingCalendar：JSON 日历（days/session）加载、无文件时工作日回退（calendar.py:17-56）；get_session/next_trading_day
- scripts/init_calendar.py：akshare tool_trade_date_hist_sina → config/trading_calendar.json；失败回退工作日

### reflection/overview.md
- ReflectionEngine.run：代码统计（compute_stats）→ LLM 归因（仅 trade_count>0）→ Memory 写入（trade_count>0 时 write_reflection）→ 日报保存（stats.py:52-90）
- ReflectionStats 口径：day_pnl=nav_end-nav_open、t_trading_pnl=SELL 已实现盈亏和、holdings_mark_pnl=day_pnl-t_pnl（近似归因）、fee_ratio=total_fees/nav_end、excess=nav_end-benchmark（stats.py:92-134）
- ReportGenerator DailyReport（report.py:19-71，schema reflection.v1；set_cash_event 字段存在但运行时未传）
- 测试：TestAcceptance12ReflectionStatsFirst

### replay/overview.md
- ReplayStore：save_tick（ticks.jsonl 追加）/save_daily_summary/load_ticks（store.py:19-69）
- ReplayRunner：replay_day 统计（ticks/fills/rejects/nav）、verify_consistency 两次读取比对（runner.py:30-97）
- Evaluator.compute_daily：回撤/超额/费用率/成功率（runner.py:115-149）
- 重点差异：save_tick 无运行时调用（TickExecutor 未录制 Replay 包）；TickRecord 模型在 src 中无构造点；验收8 用手工数据测试 ReplayRunner

### operations/cli.md
- scripts/cli.py 七条指令：ADD（上限 20）/REMOVE（持仓→入清仓队列；否则直接移池）/PAUSE、RESUME（写 data/account/mode.json——仅记录，Scheduler 不读取！差异点）/SET_CASH（无 PRD 校验）/STATUS（现价 + 最近10笔成交，见 trading/status.py）/CLEAR_ALL
- seed_account.py（--codes/--cash/--reset）、init_calendar.py、analyze_log.py（服务器事件统计，硬编码 /opt/ai-t-agent 路径）、test_llm.py、test_market.py（硬编码 /opt/ai-t-agent/src 与 002185/600584）
- manage.ps1（Windows→SSH 远程包装，pem 路径在本机，服务器 8.137.174.58）与 deploy/agent.sh（远程管理脚本）

### operations/deployment.md
- systemd：ai-t-agent.service（Restart=on-failure、RestartSec=10、EnvironmentFile=.env、ExecStart python -m agent.main）与 ai-t-agent-watchdog.service（BindsTo、Restart=always）
- install.sh：目录创建→复制→venv→seed_account→init_calendar→安装 systemd
- backup.sh：cron 15:30，state.json/memory.db/default.yaml/replay 压缩到 data/snapshots/YYYYMMDD，保留 30 日
- 生产环境：阿里云 8.137.174.58，/opt/ai-t-agent，env=prod（tmp_logs/agent.log 实证）

### operations/watchdog.md
- WatchDog：心跳检查（heartbeat.json，timeout 90s）、磁盘空间（<1GB 告警）（watchdog.py:25-89）
- 原则：隔离重启、保留账本、告警、降级、不可直接改账（docstring）
- 差异点：update_heartbeat 无调用方（主进程未写心跳）；_check_heartbeat 只记日志不主动重启（注释依赖 systemd）

### testing/overview.md
- 运行命令：python -m pytest tests/（55 passed：22 单元 + 33 验收，README 实证）
- conftest fixtures：default_config/fee_config/sample_quote（600584）/low_price_quote（2 元）
- 分层：unit（费用 7 + T+1/状态机 15）、acceptance（01: 验收1-5 共 7 例、02: 验收6-10 共 11 例、03: 验收11-15 共 15 例）；tests/integration/ 为空目录
- 边界：验收测试直接构造引擎/快照/行情，不经过 Scheduler 主循环；决策链路（LLM）不在测试内（无 mock LLM 测试）

### testing/acceptance-criteria.md
- 15 项验收标准逐一映射（PRD「核心验收标准汇总」1818-1834 行 ↔ 测试类 ↔ 源码不变量）：
  1 风控原子性（TestAcceptance01RiskAtomicity）；2 止损深度穿透（TestAcceptance02DeepStopLoss）；3 清仓跨日累计（TestAcceptance03LiquidationCrossDay）；4 费用精度（TestAcceptance04FeePrecision + unit）；5 14:57 后不执行（TestAcceptance05SessionSuspend——验证 _in_trading_session 边界）；6 基准清空重建（TestAcceptance06BenchmarkRebuild）；7 Memory 跨日（TestAcceptance07MemoryCrossDay）；8 Replay 可复现（TestAcceptance08ReplayReproducible）；9 LLM 必经 Risk（TestAcceptance09LLMMustPassRisk）；10 低置信度过滤（TestAcceptance10LowConfidenceFilter）；11 Regime 四态（TestAcceptance11MarketRegime）；12 统计先行（TestAcceptance12ReflectionStatsFirst）；13 Context 统一注入（TestAcceptance13ContextUnifiedInjection——注意运行时差异）；14 Event Log 时间线（TestAcceptance14EventLogTimeline）；15 Schema 可审计（TestAcceptance15SchemaVersion）

### references/design-docs.md
- docs/PRD：V2.0 Final，Chapter 0-13（哲学/产品定义/架构/Context/MU/大脑/记忆/交易/风控/调度/Replay/配置/部署/路线图）+ 工程规范 + 15 验收
- docs/SPEC：V1.1 Final，0-15 章（开发准则/工程结构/第一阶段模块 SPEC/领域模型/配置/日志/测试/部署/调用关系/错误码/Schema 注册表）
- 文档与代码差异提示：SPEC 中 lifecycle.py/order.py/prompt.py/writer.py/retriever.py/single_flight.py/schema_parser.py 等已合并或未独立成文件；PRD 8.4 换仓亏损联动拒绝、8.2 SET_CASH 校验未实现；PRD 14:57 后不执行由 Scheduler._dispatch 保证（tick.py 无时间判断）

## 未知未知项检查清单（撰写后复查）

- [x] `tmp_logs/` 运行时样例与存储布局一致性（已核实：event_log.jsonl 事件序列、state.json 结构、daily.json 结构）
- [x] `conversation_history/`（空目录）——在 quickstart 一句带过即可
- [x] 验收 5「14:57 后不执行」在 tick.py 中的落地 → 由 Scheduler._dispatch/_in_trading_session 边界保证，tick 无时间判断（TestAcceptance05 验证 _in_trading_session）
- [x] 验收 15 Schema 版本审计在各 dataclass 中的落地（schema_version 字段分布于 FeatureSnapshot/MemoryItem/DecisionOutput/TickRecord/DailyReport/Account.SCHEMA_VERSION）
- [x] 未接线模块清单（ContextAssembler/FeatureEngine/ReplayStore.save_tick/MemoryCompressor/WatchDog 心跳）——已在各页标注「重点差异」
- [x] CLI PAUSE/RESUME 与 Scheduler 的关系（写 mode.json 但 Scheduler 不读——记差异）
- [x] DecisionEngine 的 Prompt 构建与 ContextAssembler 的关系（内联构建，ContextAssembler 未接入——记差异）

## Backlog（显式推迟项）

- `tests/integration/` 为空目录：无可写证据，仅在与测试相关的页面提及目录存在。
- `docs/` 全文细节（62KB+98KB）：wiki 只做导航与设计原则提炼，不复制全文。
- `tmp_logs/agent.log` 的 HTTP 明细：作为生产运行证据引用（env=prod、智谱 endpoint），不逐行记录。
- 历史提交（git）：当前目录不是 git 仓库（`.last-update.json` 记录 `fatal: not a git repository`），变更历史证据不可用，wiki 以源码+测试+运行日志为准。
