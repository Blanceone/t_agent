# Personal AI Quant Trading Agent
# 产品需求文档（PRD）— V2.0 Final

| 项目 | 内容 |
| :--- | :--- |
| **产品名称** | Personal AI Quant Trading Agent |
| **内部代号** | AI-T-Agent |
| **版本** | **V2.0 Final** |
| **状态** | **Frozen — Enter Development**（PRD 冻结，进入正式开发） |
| **运行环境** | Linux Server（长期常驻） |
| **核心原则** | Rule + LLM；代码为体，模型为脑，Memory 为魂；Replay 负责成长 |
| **基线来源** | 交易制度 / 账户 / 风控继承 V19.0 Research Baseline；结构遵循 PRD Writing Specification；V1.1 增强项保留；V2.0 采纳 Final Review 工程建议 |
| **修订说明** | V2.0 Final：保持总体架构不变；补齐统一模块模板、System Context、Event Log、Schema Version、Decision 完整字段、基础 Feature 清单与 Replay 完整上下文；明确停止继续纸面设计，基于模拟盘数据驱动迭代。 |

---

# 文档目标

本文档是正式产品需求文档（PRD）的 **最终冻结版**。

用于指导：产品边界、系统设计、模块实现、测试验收与版本演进。

任何开发、设计、功能扩展，都必须遵循本文档。

本文档中的 **Chapter 0 设计哲学** 为本项目最高设计标准；后续章节不得违反。

> **Final Review 结论（2026-07-29）**  
> 本 PRD 已达到可开发 / 可维护 / 可验证 / 可成长四项核心目标。  
> **停止继续设计 PRD。开始开发。**  
> 未来改进必须基于真实模拟盘运行数据驱动（Prompt / Memory / Reflection / Feature / Replay），而不是继续扩大系统复杂度。

---

# Chapter 0 Design Philosophy（设计哲学）

## Objective

定义整个项目不可违背的最高原则。

## Scope

包含：设计哲学、职责边界、成长闭环。  
不包含：具体策略公式、接口实现、数据库选型细节（见后续章节）。

---

## Philosophy 1 — Rule + LLM

传统量化负责确定性。  
LLM 负责不确定性。

不是 Rule OR LLM，而是 **Rule + LLM**。

| 类型 | 归属 | 示例 |
| :--- | :--- | :--- |
| 有唯一答案 | 代码（Rule） | T+1、涨跌停、费用、现金预留、撮合、熔断 |
| 需要判断 | LLM | 市场理解、做 T 时机、多信号仲裁、复盘、Prompt 优化 |

---

## Philosophy 2 — Code is the Body（代码为体）

代码负责：行情、数据、Feature、风控、下单、调度、存储、日志、Replay。

所有有唯一答案的问题，全部由代码完成。  
代码是唯一真相源（Source of Truth）。

---

## Philosophy 3 — LLM is the Brain（模型为脑）

LLM 负责：市场理解、推理、做 T 策略、每日计划、仓位建议、多信号仲裁、收益分析、Reflection、Prompt 优化、长期学习。

任何需要判断的问题，交给 LLM。  
**LLM 不能直接交易**；所有决策必须经 Risk Engine 校验后，才能进入 Trading Engine。

---

## Philosophy 4 — Memory is the Soul（记忆为魂）

系统最大竞争力不是 Prompt，也不是模型，而是 Memory。

成长闭环：

```text
观察 → 计划 → 执行 → 复盘 → 总结 → Memory → 下一次决策
```

Memory 必须长期保留，不能每天重新开始。

---

## Philosophy 5 — Profit is the Result（收益是结果）

系统目标不是每天交易，也不是每天赚钱。

真正目标：在不改变用户长期持仓方向的前提下，通过日内做 T 持续降低持仓成本，**长期收益持续跑赢 Buy & Hold**。

收益是 Agent 不断成长后的自然结果。

---

# Chapter 1 Product Definition（产品定义）

## Objective

定义产品定位、系统边界、用户/Agent 职责、收益目标与成功标准。

## Scope

包含：定位、目标、职责、边界、评价体系、非目标、未来规划。  
不包含：实现细节、数据库、Prompt 全文、接口代码。

---

## 1.1 产品定位

Personal AI Quant Trading Agent：一名长期运行于 Linux Server、围绕用户已有持仓进行持续管理的 **个人 AI 交易员**。

它是：

- 陪伴式持仓管理 Agent
- 分钟级日内做 T 决策系统（连续竞价时段每分钟一次决策循环）
- 可 Replay、可审计、可持续学习的个人量化伴侣

它不是：

- 选股系统
- 高频交易（HFT）系统
- 机构量化平台
- 自动投资顾问（Robo-Advisor）

> **定位纠偏说明**：基线文档中的「1 分钟级」指决策调度粒度，不是亚秒级 HFT。产品对外名称与对外表述一律使用「Personal AI Quant Trading Agent / 日内做 T Agent」，禁止使用 HFT 作为产品定位。

---

## 1.2 产品目标

帮助用户：在不改变长期持仓方向的情况下，持续进行日内做 T，不断降低持仓成本，提高长期收益。

最终实现：**长期收益持续跑赢 Buy & Hold**。

### 初始运行参数（MVP 默认）

| 参数 | 默认值 |
| :--- | :--- |
| 初始资金 | 30,000 元人民币 |
| 市场范围 | 仅 A 股普通股 |
| 交易模式 | 全自动模拟盘（MVP） |
| 决策频率 | 连续竞价时段每分钟 1 次 |
| 股票池上限 | 20 只 |

---

## 1.3 用户职责

用户只负责：

- 管理股票池（增加 / 删除股票）
- 查看收益与分析
- 决定长期投资方向（持什么、不持什么）
- 必要时调整资金（`SET_CASH`）、暂停 / 恢复策略

用户 **不负责**：择时、资金分配、做 T 执行、风控触发、清仓执行。

---

## 1.4 Agent 职责

Agent 负责：

- 市场理解
- 每日交易计划（Planner）
- 日内做 T 决策
- 仓位调整
- 风险控制
- 自动交易执行
- 收益分析
- 每日复盘（Reflection）
- 长期学习与 Memory 维护
- Prompt 优化建议（经人工或配置确认后生效）

---

## 1.5 收益来源

| 收益来源 | 说明 |
| :--- | :--- |
| 做 T 价差 | 在持仓方向不变前提下，高抛低吸降低成本 |
| 成本摊薄 | 买入费用计入加权成本；成功做 T 降低平均成本 |
| 风险避损 | 止损 / 熔断 / 强平减少极端回撤 |
| 相对超额 | 相对等权满仓基准与沪深300全收益指数的超额收益 |

---

## 1.6 评价体系（成功标准）

| 维度 | 指标 | 成功定义 |
| :--- | :--- | :--- |
| 超额收益 | Agent NAV vs 等权 Buy&Hold vs 沪深300全收益 | 滚动 60 交易日超额收益 ≥ 0，且费用后仍为正倾向 |
| 回撤控制 | 最大回撤 | 相对 peak_nav 回撤触发规则有效；不出现未拦截的 10%+ 失控回撤 |
| 做 T 质量 | 做 T 贡献、往返费用占比 | 日报可拆分「做 T 收益 / 持仓浮动 / 费用」 |
| 风控可靠性 | 拒单率、熔断触发正确性 | 验收用例 100% 通过 |
| 可复现性 | Replay 一致性 | 同输入同配置可完整复现决策与成交 |
| 成长性 | Memory 命中与 Reflection 落地 | Memory 跨日保留；复盘结论可被次日 Planner/Decision 引用 |

---

## 1.7 系统边界

### 适用范围

- A 股普通股
- 单用户、单账户、模拟盘优先
- Linux Server 长期常驻进程

### 非目标（明确不做）

- 自动选股
- 高频做市 / 亚秒级 HFT
- ETF 套利
- 期权 / 期货 / 可转债 / 逆回购 / 衍生品
- 多账户、多用户、企业级交易平台
- 实盘收益的线性外推承诺（MVP 为零滑点撮合模型）
- 复杂 Alpha Engine / 因子工厂 / 机器学习平台（验证 LLM 交易能力前不做）

### 当前版本明确暂缓（不进入 V2.0 / 第一二阶段）

以下能力有价值，但 **不进入当前开发范围**，避免过早复杂化：

| 暂缓项 | 原因 | 建议阶段 |
| :--- | :--- | :--- |
| Alpha Engine（大量 Signal/Factor） | 当前验证 Agent，不是验证 Alpha | 未来版本 |
| Research Engine | 增加复杂度，非 MVP 必需 | 未来版本 |
| 多 Agent（Bull/Bear/Judge/Research） | 显著增加复杂度 | 未来版本 |
| 自动 Prompt 优化 | 风险高，先人工 Review | 未来版本 |
| 新闻分析 | 数据质量差、维护成本高 | 未来版本 |
| 复杂技术指标（MACD/KDJ/ATR/布林带/Alpha101 等） | 基础 Feature 已足够；按需再加 | 后续按需 |

当前版本 **保持 MVP 范围即可**，无需继续增加复杂量化模块。

---

## 1.8 未来规划（摘要）

| 阶段 | 重点 |
| :--- | :--- |
| 第一阶段（稳定底座） | Trading → Risk → Scheduler → Replay → Memory → Decision → Reflection |
| 第二阶段（计划与理解） | Planner → Market Understanding（含 Regime）→ Report → Memory 优化 |
| 第三阶段（增强） | 更多 Feature / Regime 深化 → 新闻 → Research → 多 Agent（仅数据驱动后按需） |

详细见 Chapter 13。开发顺序以「先稳定运行、再增强智能」为准，**不推倒重构，不继续扩 PRD 范围**。

---

# Chapter 2 Architecture（系统架构）

## Objective

定义系统组成方式、统一生命周期、数据流 / 控制流 / 事件流与模块职责。

## Scope

包含：架构、模块关系、生命周期、线程关系、调用顺序、Linux 运行流程。  
不包含：具体交易策略内容（见 Chapter 4–5）。

---

## 2.1 整体架构

```text
┌─────────────────────────────────────────────────────────────┐
│                    Scheduler（唯一调度中心）                   │
└─────────────────────────────────────────────────────────────┘
                              │
     ┌────────────────────────┼────────────────────────┐
     ▼                        ▼                        ▼
 Market Service          Feature Engine           WatchDog
     │                        │
     ▼                        ▼
 Market Understanding ←───────┘
     │
     ▼
 Planner（开盘前）
     │
     ▼
 Context Assembler（统一上下文）
     │
     ▼
 Decision（每分钟） ←── Context / Memory / Portfolio / Today Plan / Risk Snapshot
     │
     ▼
 Risk Engine（永远优先）
     │
     ▼
 Trading Engine → Portfolio / Account / Order / Broker(Sim)
     │
     ▼
 Reflection（日终） → Memory Update → Report → Replay Store
```

推荐闭环：

```text
Market → Feature → Market Understanding → Planner → Context
→ Decision → Risk → Trading → Portfolio → Reflection → Memory → Replay
→ 下一次决策
```

---

## 2.2 模块职责

| 模块 | 职责 | 归属 |
| :--- | :--- | :--- |
| Market Service | 行情接入、交易日历、陈旧行情判定 | 代码 |
| Feature Engine | 预计算账户/持仓/基础市场 Feature（涨跌幅、OHLC、VWAP、振幅、量能、量比、换手率等）与往返费用估算 | 代码 |
| Context Assembler | 组装 System/Market/Portfolio/Holding/Memory Context，供 Prompt 统一引用 | 代码 |
| Market Understanding | 日级市场状态、**Market Regime**、风险偏好、策略偏好 | LLM + 代码特征 |
| Planner | Today Plan（目标仓位、做 T 计划、风险等级；受 Regime 约束） | LLM |
| Decision | 分钟级交易意图（BUY/SELL/HOLD）+ **confidence / reason** | LLM |
| Risk Engine | 止损、HALT、LIQUIDATE、仓位/现金约束、**低置信度过滤**、拒单 | 代码 |
| Trading Engine | 撮合、费用、T+1、订单/成交、清仓队列 | 代码 |
| Portfolio / Account | 持仓、现金、NAV、基准组合 | 代码 |
| Reflection | 日终复盘：**代码统计先行**，LLM 解释归因；Prompt/Memory 更新建议 | 代码统计 + LLM |
| Memory | 长短期记忆存储、检索、压缩、注入 Prompt | 代码 + LLM 摘要 |
| Replay & Evaluation | 决策/成交/风控全量回放与评估 | 代码 |
| Scheduler | 唯一时间轴、任务优先级、超时与恢复 | 代码 |
| WatchDog | 进程/模型/行情/网络异常恢复 | 代码 |
| Config Center | 全量配置，禁止硬编码关键阈值 | 代码 |

---

## 2.3 双层架构原则

| 层 | 名称 | 说明 |
| :--- | :--- | :--- |
| 物理层 | 代码 | 唯一真相源：制度、记账、费用、风控、撮合 |
| 决策层 | LLM | 只能提建议；必须经物理层校验方可执行 |

---

## 2.4 生命周期（日级）

```text
09:20  日切 + Market Understanding + Planner
09:30  进入连续竞价交易循环
每分钟 Market → Feature → RiskGuard → LiquidationWorker → Context → Decision → Risk → Execution → Save → EventLog
11:30  上午休市（保持状态，不决策）
13:00  下午开盘，恢复分钟循环
14:57  系统挂起：停止决策与撮合；进行中的 LLM 输出丢弃
15:05  Stats → Reflection → Memory Update → 日报 → Replay 落盘 → EventLog
```

---

## 2.5 数据流 / 控制流 / 事件流

### 数据流

行情 Tick / Bar → Feature → Context Assembler → Prompt Context → LLM Decision JSON → Risk 校验 → Order → Fill → Account/Portfolio → Logs/EventLog/Replay

### 控制流

Scheduler 驱动；Risk 可短路跳过 LLM 或禁止 BUY；`LIQUIDATE` 时忽略 LLM。

### 事件流

用户指令（ADD/REMOVE/…）、风控事件（HALT/STOP_LOSS）、清仓事件、SET_CASH、行情异常、LLM 超时，均写入审计日志并可 Replay。

---

## 2.6 线程与调用顺序（约束）

- 全系统 **仅一个 Scheduler** 拥有交易时段主循环所有权。
- 每分钟 Tick **全同步原子执行**（见 Chapter 9）：先锁快照，再风控，再清仓，再决策。
- LLM 调用采用 **单飞行（single-flight）**：上次未返回则本分钟跳过。
- WatchDog 独立于交易主循环，不得直接改账，只能重启/告警/切换降级模式。

---

## 2.7 Linux 运行流程（摘要）

1. `systemd` 拉起主进程与 WatchDog。
2. 加载 Config → 连接行情/存储 → 校验交易日历。
3. 进入 Scheduler 主循环。
4. 异常时 WatchDog 重启对应服务；主账本以落盘状态恢复。
5. 日终备份 Account、Memory、Logs、Replay 包。

详细见 Chapter 12。

---

## Acceptance（本章）

1. 架构图与模块职责表完整，且无「LLM 直达下单」路径。
2. 生命周期覆盖 09:20 / 分钟循环 / 14:57 挂起 / 15:05 复盘。
3. 明确唯一 Scheduler 与单飞行约束。

---

# Chapter 3 Context Layer（统一上下文）

## Purpose

为 Planner / Decision / Reflection 提供统一、可版本化、可 Replay 的 Context，避免 Prompt 无限膨胀。

所有 LLM Prompt **统一引用 Context 切片**，禁止把完整账本与历史原文反复硬编码进 Prompt。

## Scope

包含：System / Market / Portfolio / Holding / Memory Context 的定义、组装、注入与版本。  
不包含：交易执行、风控硬规则判定。

---

## Architecture

```text
Account + Market + Feature + Memory Retriever + Today Plan + Risk Snapshot
                           ↓
                   Context Assembler（代码）
                           ↓
        SystemContext / MarketContext / PortfolioContext
        HoldingContext / MemoryContext
                           ↓
        Prompt Renderer（按 prompt_version 注入所需切片）
```

---

## Context 类型

| Context | 内容 | 主要消费者 |
| :--- | :--- | :--- |
| **System Context** | 日期、交易时段、`risk_state`、系统模式（NORMAL/PAUSE）、配置摘要（阈值类）、`schema_version` | 全部 LLM |
| **Market Context** | 指数概况、`market_regime`、风险等级、交易建议、量能摘要 | Planner / Decision / Reflection |
| **Portfolio Context** | `nav_mark`、现金、当日盈亏、相对基准超额、现金预留余量 | Planner / Decision / Reflection |
| **Holding Context** | 单票持仓、可卖、成本、止损距、状态、冷却、基础 Feature | Decision / Planner |
| **Memory Context** | Top-K Memory 摘要 + `memory_id` 列表（非全文倾倒） | Planner / Decision / Reflection |

---

## Input

- 账户快照、行情/Feature 快照、Market Understanding 输出、Today Plan、Risk 快照、Memory 检索结果、Prompt 所需字段清单。

## Output

```json
{
  "context_id": "ctx_20260729_093100",
  "schema_version": "context.v1",
  "system": {},
  "market": {},
  "portfolio": {},
  "holdings": [],
  "memory": { "items": [], "memory_ids": [] },
  "token_budget": { "used": 0, "max": 0 }
}
```

## Processing

1. 按 Prompt 类型选择需要的 Context 切片（不是每次全量注入）。
2. 强制长度上限（可配置）；超限按重要性截断，并记录截断事件。
3. 生成 `context_id` 与哈希，写入 Decision/Replay。

## Failure Handling

Context 组装失败 → 该分钟跳过 LLM 或使用最小 System+Portfolio 降级 Context；记 `CONTEXT_FALLBACK`。

## Logging / Replay

必须记录：`context_id`、`schema_version`、各切片哈希、截断标记、注入的 `memory_ids`。

## Acceptance

1. Prompt 不直接嵌入完整原始日志；只引用 Context。
2. Replay 可通过 `context_id` 还原当时注入内容。
3. Memory Context 携带可追溯 `memory_ids`。

---

# Chapter 4 Market Understanding（市场理解）

## Objective

Agent 每天首先理解市场与持仓环境，再进入计划与交易。  
本章只负责理解，不负责下单。

## Scope

包含：指数/量能/持仓环境分析、**Market Regime**、日级输出。  
不包含：分钟级下单决策、风控执行、复杂板块/新闻（V2+ / 最后加入）。

---

## Architecture

```text
Market Service + Feature Engine
        ↓
代码判定 Market Regime（规则优先） + LLM 文字理解
        ↓
Today Market Summary / Regime / Risk Level / Trading Suggestion / Strategy Preference
        ↓
注入 Planner 与当日 Decision Context
```

---

## 4.1 Market Regime（简单四态）

系统必须产出当日主 Regime（可附次级标签），供 Planner 调整做 T 频率、仓位与风险等级。

| Regime | 含义 | 对 Planner 的默认约束（可配置） |
| :--- | :--- | :--- |
| `TREND` | 趋势市 | 允许更高做 T 频率；顺势偏向；目标仓位可略积极 |
| `RANGE` | 震荡市 | 标准做 T；强调高抛低吸；避免追涨杀跌 |
| `HIGH_VOL` | 高波动 | 降低做 T 频率与单笔规模；提高 risk_level；偏防御 |
| `LOW_VOL` | 低波动 | 降低无效往返；提高费用敏感性；减少勉强做 T |

### Regime 判定原则

- **代码规则优先**生成候选 Regime（基于指数涨跌、振幅、量比等基础 Feature）。
- LLM 可确认或微调，但必须输出枚举值之一；非法则回退代码结果。
- 降级时默认：`RANGE` + `risk_level=MEDIUM` + `strategy_preference=CONSERVATIVE`。

> 不引入复杂状态机或多因子 Regime 引擎；四态足够支撑个人做 T Agent。

---

## Workflow

1. 09:20 日切完成后触发。
2. 代码汇总：指数点位与涨跌、量能、用户 watchlist 涨跌分布、基础 Feature、昨日 Reflection 摘要、相关 Memory；并给出 Regime 候选。
3. LLM 输出结构化「今日市场理解」（含最终 `market_regime`）。
4. 结果写入 Short Memory，并作为 Planner 输入。
5. 若 LLM 超时/失败：使用规则降级（Regime=`RANGE`，Risk Level=`MEDIUM`，Strategy Preference=`CONSERVATIVE`），不阻断后续日切与交易准备。

---

## Data Structure（输出）

```json
{
  "date": "2026-07-28",
  "today_market_summary": "……",
  "market_regime": "TREND|RANGE|HIGH_VOL|LOW_VOL",
  "regime_secondary": ["HIGH_VOL"],
  "today_risk_level": "LOW|MEDIUM|HIGH",
  "today_trading_suggestion": "ACTIVE_T|REDUCE_T|DEFENSIVE|NO_NEW_BUY",
  "today_strategy_preference": "AGGRESSIVE|BALANCED|CONSERVATIVE",
  "index_view": { "csi300": { "bias": "up|down|range", "note": "…" } },
  "holdings_context": { "pressure": "…", "opportunity": "…" },
  "confidence": 0.0
}
```

第一阶段可先实现：指数涨跌、持仓涨跌分布、量能相对均值、昨日盈亏结构、四态 Regime；板块/热点/资金流/新闻在后续阶段增强。

---

## Exception Handling

| 异常 | 处理 |
| :--- | :--- |
| 行情缺失 | 降级规则输出 + 告警 |
| LLM 超时 | 降级规则输出；记录 `MU_FALLBACK` |
| 输出 Schema 不合法 / Regime 非法 | 重试 1 次；仍失败则采用代码 Regime 候选 |

---

## Logging

`market_understanding.jsonl`：输入特征摘要、Regime（代码候选与最终值）、输出 JSON、是否降级、耗时。

---

## Acceptance

1. 每个交易日 09:20 后必须产生今日市场理解（或明确降级标记），且 `market_regime` 为四态之一。
2. 输出可被 Planner 引用；不产生任何交易指令。
3. Planner 在 `HIGH_VOL` 下默认降低做 T 频率（可通过配置验证）。

---

# Chapter 5 Agent Brain（AI 大脑）

## Objective

定义 Planner / Decision / Reflection 三层大脑，以及 Prompt、Tool、Schema 与异常处理。

## Scope

包含：开盘计划、分钟决策、日终复盘、Prompt 管理。  
不包含：撮合与记账（Trading）、最终放行（Risk）。

**硬约束：LLM 不能直接交易，必须经过 Risk。**

---

## 5.1 Planner（开盘前）

### Objective

每天开盘前制定 Today Plan。

### Workflow

09:20 市场理解完成后：

1. 读取 Portfolio、Memory、Market Understanding（含 **`market_regime`**）、风险状态。
2. 按 Regime 调整计划约束：做 T 频率上限、目标仓位带、风险等级默认值。
3. LLM 为 watchlist 中每只股票生成计划。
4. 计划写入当日上下文，供分钟 Decision 使用。
5. 失败则使用保守默认计划（低做 T 频率、禁止追涨）；`HIGH_VOL` 时进一步收紧。

### Data Structure

```json
{
  "date": "2026-07-28",
  "market_regime": "RANGE",
  "plans": [
    {
      "code": "600584",
      "trade_plan": "高抛低吸，优先卖出可卖仓做 T",
      "target_position_ratio": 0.25,
      "t_strategy": "SELL_FIRST_THEN_BUY_BACK",
      "risk_level": "MEDIUM",
      "max_trades_hint": 4,
      "notes": "…"
    }
  ],
  "cash_plan": { "min_cash_ratio": 0.20 },
  "global_bias": "BALANCED"
}
```

---

## 5.2 Decision（每分钟）

### Objective

在连续竞价有效时段，结合最新行情、Today Plan、Memory、Portfolio、Risk Snapshot，输出交易意图。

### 有效时段（物理层）

- **09:30–11:30 / 13:00–14:57**：唯一允许 LLM 决策并进入撮合校验的时段。
- **09:15–09:25**：开盘集合竞价，不产生指令。
- **14:57–15:00**：收盘集合竞价，系统挂起；若 LLM 仍在调用，等待完成后 **丢弃输出**。

### 输入（由 Feature Engine 预计算注入）

#### A. 账户与持仓 Feature

1. `nav_mark`、当日盈亏率、基准比对。
2. 各标的：`sellable_shares`、距止损百分比、`position_state`、成本价。
3. Today Plan 摘要、相关 Memory 摘要（含 memory_id 列表）、`risk_state`、`market_regime`。

#### B. 基础市场 Feature（每标的，易计算、低成本）

| Feature | 说明 |
| :--- | :--- |
| `pre_close` | 昨日收盘价 |
| `open` | 今日开盘价 |
| `high` | 今日最高价 |
| `low` | 今日最低价 |
| `last` | 最新价 |
| `open_chg_pct` | 开盘涨跌（相对昨收） |
| `chg_pct_1d` | 今日涨跌幅 |
| `chg_pct_5d` | 5 日涨跌幅 |
| `chg_pct_10d` | 10 日涨跌幅 |
| `vwap` | 当日 VWAP |
| `amplitude` | 今日振幅 `(high-low)/pre_close` |
| `volume` | 今日成交量 |
| `volume_ratio` | 量比（相对近期均量） |
| `turnover_rate` | 换手率（可得则给；缺失则标记 null） |

> 仅注入上述基础 Feature。**不引入** MACD / KDJ / ATR / 布林带 / Alpha101 等复杂技术指标或 Alpha 因子工厂。MVP 已足够。

#### C. 往返费用估算 `round_trip_fee_est`（100 股买+卖）

```text
max(买入额×0.00025, 5) + 买入额×0.00001
+ max(卖出额×0.00025, 5) + 卖出额×0.0005 + 卖出额×0.00001
```

买入额/卖出额使用 `ask1`/`bid1`，缺失时用 `last` 回退。  
该公式必须体现最低佣金 5 元，防止低价股做 T 偏差。

### 输出 Schema

```json
{
  "thought_process": "...",
  "decisions": [
    {
      "action": "BUY|SELL|HOLD",
      "code": "600584",
      "shares": 100,
      "confidence": 0.82,
      "reason": "接近日内高位且可卖仓充足，先高抛做 T",
      "risk_level": "LOW|MEDIUM|HIGH",
      "referenced_memory": ["mem_20260728_001", "mem_20260727_014"]
    }
  ]
}
```

字段约束：

| 字段 | 要求 |
| :--- | :--- |
| `confidence` | `[0, 1]` 浮点数；缺失或非法视为 `0` |
| `reason` | 非空短句，说明本条决策理由 |
| `risk_level` | 本条决策自评风险；缺失则默认 `MEDIUM` |
| `referenced_memory` | 本条实际引用的 Memory ID 列表（可空数组）；须与注入的 Memory Context 子集一致 |
| `action=HOLD` | `shares` 可为 0；仍建议给 confidence/reason/risk_level |

作用：Risk 过滤低质量决策；Replay 分析 Decision 质量；Evaluation 更准确。

### Decision 流程

1. 校验是否在有效时段、是否单飞行空闲、行情是否新鲜。
2. 组装 Context（见 Chapter 3），按 Decision Prompt 版本渲染。
3. 若 `risk_state == LIQUIDATE`：跳过 LLM。
4. 若 `risk_state == HALT`：Prompt 注入 HALT，仅允许 `ACTIVE` 标的 SELL。
5. 若 `PAUSE`：跳过 LLM（清仓任务仍继续）。
6. 调用 LLM → Schema 校验（含 confidence/reason/risk_level/referenced_memory）→ 失败重试 1 次 → 仍失败则本分钟 `HOLD`。
7. 决策进入 Risk Engine（含 **confidence 阈值过滤**），不得绕过。

---

## 5.3 Reflection（收盘后）

### Objective

先由代码产出客观统计，再由 LLM 解释归因，提出 Memory / Prompt 更新建议。

### Workflow（15:05）

1. **代码自动统计**（客观层，不依赖 LLM）：
   - 今日收益、做 T 收益、持仓浮动、相对基准超额
   - 手续费及手续费占比
   - 卖飞次数、止损次数、HALT/拒单次数
   - 平均持仓时间、Decision 成功率（或成交成功率）、低置信度过滤次数
   - SET_CASH 事件与其对净值的被动影响
2. 将统计结果注入 Reflection Prompt（`Reflection Prompt vX.Y`）。
3. **LLM 负责解释**：为什么赚钱/亏钱、哪些判断对错、是否需更新 Memory/Prompt。
4. 生成 Memory 候选条目（需经写入策略确认，见 Chapter 6）。
5. 生成 Prompt 优化建议（默认不自动覆盖生产 Prompt；需人工确认；自动优化不在当前版本）。

### Data Structure（摘要）

```json
{
  "date": "2026-07-28",
  "stats": {
    "day_pnl": 0.0,
    "fee_ratio": 0.0,
    "t_trading_pnl": 0.0,
    "holdings_mark_pnl": 0.0,
    "sold_too_early_count": 0,
    "stop_loss_count": 0,
    "avg_holding_minutes": 0.0,
    "decision_success_rate": 0.0,
    "low_confidence_hold_count": 0,
    "set_cash_effect": 0.0
  },
  "what_worked": ["…"],
  "what_failed": ["…"],
  "pnl_attribution": {
    "t_trading": 0.0,
    "holdings_mark": 0.0,
    "fees": 0.0,
    "set_cash_effect": 0.0
  },
  "memory_candidates": [],
  "prompt_change_suggestions": [],
  "score": { "decision_quality": 0.0, "risk_discipline": 0.0 }
}
```

原则：**Statistics → LLM Analysis → Memory**。统计归代码，解释归 LLM。禁止仅用 LLM 口头编造关键数值。

---

## 5.4 Prompt 管理（版本强制）

所有 Prompt 必须带版本号，例如：

| Prompt | 初始版本示例 |
| :--- | :--- |
| Market Understanding Prompt | `v1.0` |
| Planner Prompt | `v1.0` |
| Decision Prompt | `v1.0` |
| Reflection Prompt | `v1.0` |

| 项 | 要求 |
| :--- | :--- |
| 版本化 | 每个 Prompt 有 `prompt_id` + `version`（如 `decision.v1.0`） |
| 可 Replay | 决策日志记录所用 Prompt 版本与渲染后哈希 |
| 可回滚 | 支持切换历史版本 |
| Context 注入 | Prompt 只引用 Chapter 3 Context 切片，禁止无限堆原文 |
| 禁止 | 业务常量（费率、止损比例等）写死在 Prompt；应来自 Config/Feature |

---

## 5.5 Tool Calling（可选演进）

第一阶段：以结构化 Prompt + Context 注入为主。  
第二阶段起：可增加只读 Tool（查询持仓、查询 Memory、查询当日计划），**禁止** Tool 直接下单。

---

## Exception Handling

| 场景 | 处理 |
| :--- | :--- |
| Schema 非法 | 重试 1 次，否则 HOLD |
| `confidence` 缺失/非法 | 视为 0，交由 Risk 过滤 |
| `referenced_memory` 含未注入 ID | 校验失败，重试或剔除非法 ID |
| 超时 | 本分钟跳过，记 `LLM_TIMEOUT` |
| 14:57 后返回 | 丢弃 |
| HALT 下输出 BUY | Risk 拒绝，记 `REASON_HALT` |
| `confidence < threshold` | Risk 将 BUY/SELL 降为 HOLD，记 `REASON_LOW_CONFIDENCE` |

---

## Logging

`decision_log.jsonl` 必须包含：时间、`risk_state_snapshot`、`context_id`、Prompt 版本、**输入 Feature 快照/哈希**、**引用 Memory ID 列表**、输出 JSON（含 confidence/reason/risk_level/referenced_memory）、校验结果与拒单原因。

---

## Acceptance

1. HALT 当日分钟决策不得产生可执行 BUY。
2. 14:57 后无任何指令执行。
3. Decision 输出 100% 经 Risk；日志可 Replay。
4. `confidence < decision_confidence_threshold` 的 BUY/SELL 不得成交，记为 `REASON_LOW_CONFIDENCE`。
5. Reflection 的 `stats` 由代码生成，与成交账本一致。
6. Decision 必含 `confidence` / `reason` / `risk_level` / `referenced_memory` 字段。

---

# Chapter 6 Memory System（记忆系统）

## Objective

建立 Agent 长期成长能力，使决策可继承历史经验。

## Scope

包含：各类 Memory、更新/检索/压缩/生命周期、与 Prompt 关系。  
不包含：交易执行本身。

**注意事项：Memory 必须长期保留，不能每天重新开始。**

---

## Architecture

```text
Trade / Reflection / Market / Portfolio 事件
                ↓
        Memory Writer（规则 + LLM 摘要）
                ↓
     Store（长期持久化）
                ↓
        Retriever → 注入 Planner / Decision / Reflection
```

---

## Memory 类型

| 类型 | 内容 | 保留策略 |
| :--- | :--- | :--- |
| Long Memory | 稳定规律、长期偏好、重大教训 | 长期 |
| Short Memory | 当日市场理解、Today Plan、盘中观察 | 当日为主，部分晋升 |
| Market Memory | 市场状态与应对效果 | 长期，可压缩 |
| Portfolio Memory | 持仓行为、调仓后果 | 长期 |
| Reflection Memory | 复盘结论 | 长期 |
| Trade Memory | 关键成交与做 T 结果 | 长期原始 + 摘要 |
| Holding Memory | 单票成本、止损史、冷却、清仓原因 | 与标的生命周期绑定 |

---

## Workflow

### 更新

- 日终 Reflection 产生候选 → 去重 / 冲突检测 → 写入。
- 风控重大事件（STOP_LOSS、HALT、LIQUIDATE）立即写入 Holding/Trade Memory。

### 检索

- 按 code、日期、标签、相似度（V2可用向量）检索 Top-K。
- 注入 Prompt 时有长度上限（可配置）。

### 压缩

- 定期将旧 Short/Trade 细节压缩为摘要，保留原始日志在 Replay 存储中可查。

### 生命周期

- 用户 REMOVE 且清仓完成：Holding Memory 归档，不删除历史。
- 冷却期信息保留至冷却结束并归档。

---

## Data Structure（条目示例）

```json
{
  "memory_id": "mem_20260728_001",
  "type": "REFLECTION",
  "codes": ["600584"],
  "created_at": "2026-07-28T15:10:00+08:00",
  "ttl_days": null,
  "tags": ["stop_loss", "false_break"],
  "content": "……",
  "source": "reflection_v1",
  "importance": 0.8
}
```

---

## Configuration

| 配置项 | 示例 | 说明 |
| :--- | :--- | :--- |
| `memory_inject_max_tokens` | 1500 | 注入上限 |
| `memory_top_k` | 8 | 检索条数 |
| `memory_compress_after_days` | 30 | 压缩阈值 |

---

## Exception Handling

Memory 读写失败不得阻断交易主循环；降级为空 Memory + 告警。

---

## Logging

`memory_log.jsonl`：写入、检索命中、压缩、注入被截断等事件。

---

## Acceptance

1. 跨日重启后 Memory 仍可加载。
2. 次日 Planner/Decision 能引用昨日 Reflection Memory。
3. 原始交易事实不因压缩而不可审计（Replay 可查）。

---

# Chapter 7 Trading Engine（交易系统）

## Objective

负责账户真相、撮合执行、费用结算与持仓状态，确保 A 股制度正确。

## Scope

包含：Account、Portfolio、Position、Order、Trade、Cash、NAV、PnL、手续费、Settlement、清仓、重试。  
不包含：策略判断（Brain）、最终风控策略定义（Risk，但执行层必须服从 Risk）。

**所有交易必须经过 Risk。**

---

## 7.1 A 股交易制度（物理层硬编码）

### 交易日与时间

- 交易日：周一至周五，法定节假日休市（`trading_calendar.json`）。
- 日历增强：`session` 字段为 `full` / `am_only` / `pm_only`。
- 所有交易日 **09:20** 执行日切。

| 时段 | 系统行为 |
| :--- | :--- |
| 09:15–09:25 | 开盘集合竞价，不产生指令 |
| 09:30–11:30 / 13:00–14:57 | 连续竞价：决策与撮合唯一有效时段 |
| 14:57–15:00 | **挂起态**：停止决策与撮合；进行中 LLM 输出丢弃；未完成清仓挂起至次日 |

### T+1 与可卖数量

| 字段 | 含义 |
| :--- | :--- |
| `total_shares` | 总持仓 |
| `sellable_shares` | 当前可卖；日初解冻后等于 `total_shares`；卖出减少；当日买入不增加 |
| `today_bought` | 今日买入数量（T+1 锁定） |

### 涨跌停与异常拒单

| 条件 | 原因码 | 处理 |
| :--- | :--- | :--- |
| `ask1 >= limit_up` | `REASON_LIMIT_BOARD` | 禁止对应方向 |
| `bid1 <= limit_down` | `REASON_LIMIT_BOARD` | 禁止对应方向 |
| 无 ask1 / 无 bid1 | `REASON_NO_QUOTE` | 拒绝，可下分钟重试 |
| `is_suspended == true` | `REASON_SUSPENDED` | 禁止对应方向 |

### 最小交易单位与零股

- 买入：必须 100 股整数倍。
- 卖出：常规卖出禁止产生零股；**仅清仓场景允许零股**。

---

## 7.2 账户与成本模型（唯一真理）

### Account 状态结构

```json
{
  "account_id": "sim_001",
  "base_currency": "CNY",
  "initial_cash": 30000.00,
  "cash": { "available": 12000.00, "reserved_min_ratio": 0.20 },
  "positions": [
    {
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
  ],
  "watchlist": {
    "600584": { "cooldown_until_date": null }
  },
  "risk_state": "NORMAL",
  "last_nav_date": "2026-07-26",
  "last_nav": 30000.00,
  "peak_nav": 30000.00,
  "liquidation_queue": [],
  "benchmark_portfolio": {
    "equal_weight": { "nav": 30000.00, "constituents": {} },
    "csi300": { "nav": 30000.00, "index_value": 3500.0 }
  }
}
```

### NAV 口径

- **盯市净值 `nav_mark`**（风控与基准）：  
  `nav_mark = cash.available + Σ(mark_price * total_shares)`  
  盯市价格回退：`bid1` → `last` → `pre_close`
- **展示净值 `nav_display`**：用 `last`，仅前端展示。

### 基准组合

**等权组合（Buy & Hold 上限参考）**

- 构成：100% 股票市值，无现金拖累。
- **再平衡**：每日 09:20，若 watchlist 发生 ADD/REMOVE，**清空所有虚拟持仓**，再按当前 watchlist 成分 `pre_close` **全仓重新等权分配**（清空重建，非增量）。
- 估值：日终及决策前用 `mark_price` 重估。

**沪深300基准**

- 数据源：沪深300 **全收益指数**（含股息再投）。
- 更新：`基准净值_n = 基准净值_{n-1} * (指数收盘价_n / 指数收盘价_{n-1})`

### 成本口径：加权平均成本法

**买入**

- 成交金额 = `price * shares`
- 买入费用 = 佣金（万 2.5，最低 5 元）+ 过户费（万 0.1）
- 新成本价 = `(原成本×原数量 + 买入金额 + 买入费用) / (原数量 + 买入数量)`
- 成本变更后：`stop_loss_price = 新成本价 × 0.92`

**卖出**

- 成本价不变
- 已实现盈亏 = `(卖出价 - 成本价) × 数量 - 卖出费用`

### 费用模型

| 费用 | 规则 |
| :--- | :--- |
| 印花税 | 卖出金额 0.05% |
| 过户费 | 成交金额 0.001% |
| 佣金 | 双边万 2.5，单笔最低 5 元 |

---

## 7.3 持仓状态机

| 状态 | 含义 | 允许操作 |
| :--- | :--- | :--- |
| `ACTIVE` | 正常交易 | 买、卖、做 T（受冷却约束） |
| `PENDING_CLEAR` | 待清仓 | 禁止买入；代码接管卖出 |
| `CLEARING` | 清仓中 | 仅卖出 |
| `LIQ_FAIL` | 清仓失败（重试耗尽） | 告警；禁止买入；人工介入或次日策略处理 |

### 状态迁移

| 触发源 | 迁移 | 清仓后 |
| :--- | :--- | :--- |
| 用户 `REMOVE` | → `CLEARING`，`exit_reason=USER_REMOVE` | 清零后 **移出池**（不冷却） |
| Risk 止损 | → `CLEARING`，`exit_reason=STOP_LOSS` | 清零后 **留池**，`cooldown_until_date=当前日期` |
| `LIQUIDATE` 强平 | → `CLEARING`，`exit_reason=LIQUIDATE`；清空队列并优先强平 | 仅清空仓位 |

冷却校验：`cooldown_until_date >= 当前日期` 时禁止 BUY，原因 `REASON_COOLDOWN`。  
次日 09:20：若 `当前日期 > cooldown_until_date`，清除冷却字段。

---

## 7.4 订单 / 成交 / 撮合

### 撮合规则（MVP）

- 买入按 `ask1`、卖出按 `bid1`（对手价）。
- 清仓拆单：每分钟最多卖 `max_liquidation_shares_per_tick`；全成或全不成。
- **零滑点声明**：MVP 为零滑点模型，收益不可直接线性外推实盘；实盘需冲击成本模型。

### 清仓重试

- `LiquidationWorker` 消费 `liquidation_queue`。
- 连续 **30 分钟**未成交（`max_liquidation_attempts`，**跨交易日累计，不清零**）→ 撤销任务，标记 `LIQ_FAIL` 并告警。

---

## 7.5 用户指令集

| 指令 | 功能 | 约束 |
| :--- | :--- | :--- |
| `ADD` | 加入股票池 | 上限 20 |
| `REMOVE` | 移除股票 | 触发清仓，不冷却，清空后移出池 |
| `CLEAR_ALL` | 清仓清池 | 同 REMOVE 批量 |
| `PAUSE` | 暂停策略 | 跳过 LLM，清仓继续 |
| `RESUME` | 恢复交易 | 对 HALT 有效 |
| `SET_CASH` | 调整资金 | 见 Chapter 8 |
| `STATUS` | 账户/持仓/股票池现价 + 最近10笔成交 | 只读；现价拉行情，成交读 `agent.log` 的 `order_filled` |

---

## 7.6 行情字段

`code, name, last, bid1, ask1, high, low, open, pre_close, limit_up, limit_down, volume, turnover, vwap, is_suspended, is_st`

---

## Exception Handling

| 异常 | 处理 |
| :--- | :--- |
| 部分字段缺失 | 跳过 LLM，记 `HOLD` |
| 行情时间戳偏差 > 5 秒 | 跳过 LLM，记 `SKIP_STALE` |
| 撮合失败 | 拒单原因入日志，可下分钟重试（清仓受重试上限约束） |

---

## Logging

成交、拒单、费用、状态迁移全部入 `trade_log.jsonl` / `order_log.jsonl`。

---

## Acceptance

1. T+1：当日买入不可卖。
2. 常规卖出不产生零股；清仓允许零股。
3. watchlist 变更时等权基准执行「清空重建」。
4. 清仓重试跨日累计至 30 后 `LIQ_FAIL` 告警。

---

# Chapter 8 Risk Engine（风控）

## Objective

保护账户，而不是限制 Agent 成长。  
**Risk 永远优先。**

## Scope

包含：账户/仓位/现金风险、止损、连续亏损、回撤、熔断、恢复、风险等级。  
不包含：策略收益优化。

### 风控流程

```text
Decision → Risk → Execution
```

---

## 8.1 三级风控状态

| 状态 | 触发条件 | 行为 | LLM 权限 | 恢复条件 |
| :--- | :--- | :--- | :--- | :--- |
| `NORMAL` | 默认 | 正常交易 | 全权（仍经校验） | - |
| `HALT` | 日亏损率 ≥ 3%（盯市）**或** 累计已实现亏损 ≥ 500 元 | 禁止开新仓 | 仅允许 ACTIVE 标的 SELL | 次日 09:20 或 `RESUME` |
| `LIQUIDATE` | 总资产回撤 ≥ 10%（相对 `peak_nav`） | 强制平仓 | 忽略 LLM | 仓位为 0 后 |

### 公式

- 日亏损率：`day_loss_ratio = (last_nav - nav_mark) / last_nav`  
  `last_nav` 为前一交易日日终盯市净值；`>= 0.03` 触发 HALT。
- 累计已实现亏损：当日所有 SELL 的 `realized_pnl` 之和；`sum(realized_pnl) <= -500` 触发 HALT。
- 回撤：`(peak_nav - nav_mark) / peak_nav >= 0.10` 触发 LIQUIDATE。

---

## 8.2 SET_CASH

```text
SET_CASH(amount):
  market_value = Σ (mark_price * total_shares)
  // 保留调整前净值的 10% 作为安全垫
  require amount >= market_value + nav_mark_before * 0.10

  cash.available = amount - market_value
  initial_cash = amount
  last_nav = amount
  peak_nav = amount
```

**风控影响标记**：`SET_CASH` 重置 `last_nav`，可能稀释日亏损率敏感性。日报必须高亮该事件，区分资金注入与策略盈亏。

---

## 8.3 止损

- 初始化：建仓时 `stop_loss_price = cost_price * 0.92`
- 触发价：优先 `bid1`，回退 `mark_price`
- **深度穿透加速**（`enable_deep_stop_loss`，默认 `false`）：  
  `bid1 <= stop_loss_price * 0.98` 立即触发；无 `bid1` 时用 `mark_price` 同样判定，无需等 2 分钟
- **常规确认**：连续 2 分钟触发（`stop_breach_count >= 2`）；未触发则归零
- 执行：入清仓队列，迁移状态

---

## 8.4 仓位与资金约束

### 20% 现金预留

- 校验时点：Tick 开始快照
- `available_cash - (预买金额 + 预估费用) >= nav_mark * 20%`

### 单票上限

- `mark_price * total_shares <= nav_mark * 50%`

### 做 T 约束

- `enforce_intraday_buy_limit` 默认 `false`
- 若 `true`：同分钟 BUY 数量 ≤ 已成交 SELL 数量；无 SELL 的建仓豁免
- 日报统计「潜在日内回转次数」

### 换仓亏损联动拒绝

- 同分钟内，若 `est_pnl < 0` 的非风控 SELL 后存在跨标的 BUY，拒绝 BUY
- `est_pnl = (bid1 - cost_price) * shares - est_fees`

### 低置信度过滤（Decision Confidence）

```text
if action in {BUY, SELL} and confidence < decision_confidence_threshold:
    reject / rewrite as HOLD
    reason = REASON_LOW_CONFIDENCE
```

| 项 | 规则 |
| :--- | :--- |
| 配置项 | `decision_confidence_threshold`（默认建议 `0.60`，可调） |
| 适用范围 | 非风控强制单（止损/强平清仓 **不受** 此阈值限制） |
| 缺失 confidence | 视为 `0`，触发过滤 |
| 目的 | 减少随机决策，增强 Risk 过滤能力 |

---

## 8.5 风险等级（对 Brain 的建议输入）

由 Market Understanding / Planner 产出 `LOW|MEDIUM|HIGH`，并可叠加 `market_regime`；Risk Engine 仍以硬规则为准；风险等级与 Regime 只影响 LLM 行为偏好，不能绕过硬风控。

---

## Exception Handling

风控模块异常时进入 **fail-closed**：禁止新开仓，允许或优先执行已有清仓；告警。

---

## Logging

所有拒单必须有原因码（含 `REASON_LOW_CONFIDENCE`）；`decision_log` 记录更新后的 `risk_state_snapshot` 与 confidence。

---

## Acceptance

1. Tick 内触发 HALT 后，本分钟 Prompt 中 `risk_state` 为 HALT，且无 BUY 成交。
2. 无 `bid1` 但 `mark_price` 击穿止损 2%（深度开关开启）立即止损。
3. SET_CASH 当日日报有高亮标记。
4. `confidence < threshold` 的主动 BUY/SELL 被拒绝或改写为 HOLD，清仓强平不受影响。

---

# Chapter 9 Scheduler（调度中心）

## Objective

统一整个系统生命周期。全系统只能存在一个 Scheduler。

## Scope

包含：任务、优先级、超时、重试、异常恢复、完整时间轴。  
不包含：策略内容。

---

## 9.1 时间轴

### 09:20 日切

1. T+1 解冻（`sellable_shares = total_shares`，`today_bought = 0`）
2. 清零 `stop_breach_count`
3. 清理过期冷却期
4. 检查 `PENDING_CLEAR` / 未完成清仓
5. 等权基准若 watchlist 变更则清空重建
6. Market Understanding
7. Planner

### 09:30–11:30 / 13:00–14:57 每分钟 Tick（全同步原子性）

1. **锁定快照**：`account_state` + `risk_state`
2. **行情检查**：缺字段 → `HOLD`；时间差 > `stale_quote_threshold_sec`(5s) → `SKIP_STALE`
3. **RiskGuard 扫描**：止损 / HALT；若触发，**立即更新快照中的 risk_state**
4. **LiquidationWorker**：消费清仓队列
5. **组装 Context**（Chapter 3）
6. **LLM Decision**：基于更新后快照；单飞行；HALT/LIQUIDATE/PAUSE 分支
7. **Risk 校验 Decision**
8. **Execution + Save**
9. **写 Event Log 里程碑**

### 14:57–15:00

系统挂起；LLM 输出丢弃。

### 15:05 日终

1. 计算 `nav_mark`，更新 `peak_nav`
2. **代码统计** Reflection stats
3. Reflection（LLM 解释）
4. Memory Update
5. 日报：净值曲线、基准对比、拒单率、费用率、做 T 贡献、低置信度过滤次数、**SET_CASH 高亮**
6. Replay 包落盘（含完整上下文）
7. Event：`Reflection Finished` / `Day Close Finished`

---

## 9.2 优先级（高 → 低）

1. 安全停止 / 挂起边界（14:57）
2. RiskGuard / LIQUIDATE
3. LiquidationWorker
4. 日切任务
5. Decision
6. Reflection / 报表（日终）

---

## 9.3 锁、超时、重试

| 项 | 规则 |
| :--- | :--- |
| 账户锁 | Tick 内互斥，禁止并行改账 |
| LLM 超时 | 可配置；超时跳过本分钟 |
| 清仓重试 | 跨日累计至 `max_liquidation_attempts` |
| 单飞行 | 上次 LLM 未返回则跳过 |

---

## 9.4 Event Log（系统事件日志）

除业务日志外，必须有统一 **Event Log**，用于定位系统问题（非策略问题）。

示例事件：

```text
09:20 SCHEDULER_DAY_START
09:20 MARKET_UNDERSTANDING_FINISHED
09:20 PLANNER_FINISHED
09:30 TRADING_SESSION_START
09:31 CONTEXT_ASSEMBLED
09:31 DECISION_FINISHED
09:31 RISK_PASSED | RISK_REJECTED
09:31 EXECUTION_FINISHED
14:57 SESSION_SUSPEND
15:05 REFLECTION_STATS_READY
15:05 REFLECTION_FINISHED
15:05 MEMORY_UPDATE_FINISHED
15:05 REPLAY_PACKAGE_SAVED
15:05 DAY_CLOSE_FINISHED
```

| 要求 | 说明 |
| :--- | :--- |
| 格式 | `event_log.jsonl`：timestamp、event、tick_id/date、latency_ms、status、detail |
| 粒度 | 关键阶段开始/结束/失败必须有事件 |
| 用途 | 排查卡住、超时、跳过、风控短路 |

---

## Exception Handling

Scheduler 自身异常由 WatchDog 拉起；恢复时从最近落盘快照加载，不重放未确认成交。

---

## Logging

`scheduler_log.jsonl` + `event_log.jsonl`：每个 Tick 阶段耗时、跳过原因、风控变更、里程碑事件。

---

## Acceptance

1. 不存在第二个并行交易调度器。
2. Tick 顺序固定且可测：快照→行情→风控→清仓→Context→决策→执行。
3. 14:57 后无执行。
4. Event Log 可还原当日关键里程碑时间线。

---

# Chapter 10 Replay & Evaluation（回放与评估）

## Objective

支持学习、Debug、收益分析；Replay 必须完全可复现。

## Scope

包含：Decision/Prompt/Trade/Memory/Risk Replay；超额收益、回撤、手续费、做 T 收益；日报/周报/月报；Agent 评分。

---

## Architecture

```text
运行期事件流 → Replay Store（不可变）
                    ↓
            Replay Runner（同配置重放）
                    ↓
        Evaluation（超额/回撤/费用/评分）
```

---

## 必须可 Replay 的对象（完整还原一次交易）

Replay 不仅记录成交，必须能完整还原决策链路：

| 环节 | 必须落盘 |
| :--- | :--- |
| Prompt Version | `prompt_id` + `version` + render hash |
| Feature Snapshot | 输入 Feature 快照或等价哈希 + 可还原快照 |
| Memory Snapshot | 注入的 Memory Context / `memory_ids` |
| Context | `context_id` + schema_version |
| Confidence | 决策置信度 |
| Decision | 完整输出（含 reason / risk_level / referenced_memory） |
| Risk | 放行/拒单结果与原因码 |
| Execution | 订单意图与执行状态 |
| Trade Result | 成交/费用/持仓变化 |

原则：**Replay 始终能够完整还原一次交易，真正成为系统 Debug 工具。**

---

## 10.1 Decision 引用信息（Debug 必备）

每条 Decision Replay 记录必须可回答：「当时看了什么、用了什么、有多确信」。

| 字段 | 说明 |
| :--- | :--- |
| `memory_refs` / `referenced_memory` | 本决策引用的 Memory ID 列表 |
| `prompt_id` / `prompt_version` | 使用的 Prompt |
| `prompt_render_hash` | 渲染后 Prompt 哈希 |
| `feature_snapshot` 或 `feature_hash` | 输入 Feature（可存精简快照 + 全量哈希） |
| `context_id` | 统一 Context |
| `market_regime` | 当日 Regime |
| `confidence` | 决策置信度 |
| `reason` | 决策理由 |
| `risk_level` | 决策自评风险 |
| `risk_result` | 放行 / 拒单原因码（含 `REASON_LOW_CONFIDENCE`） |
| `execution_result` | 是否下单、数量、对手价 |
| `trade_result` | 成交结果与费用 |

有了上述引用信息，Debug 效率显著提高，且支持「Memory/Prompt/Feature 变更前后」对照。

---

## 评估指标

| 类别 | 指标 |
| :--- | :--- |
| 收益 | NAV、相对等权、相对沪深300全收益超额 |
| 风险 | 最大回撤、HALT/LIQUIDATE 次数 |
| 成本 | 费用率、低价股最低佣金影响 |
| 做 T | 做 T 收益贡献、潜在日内回转次数、卖飞次数 |
| Agent | 决策质量分、风控纪律分、低置信度过滤率（来自 Reflection 统计 + 规则） |

---

## 报表

- 日报（15:05 必备）
- 周报 / 月报（第二阶段）
- SET_CASH 与策略盈亏必须分列
- 日报需包含代码统计层关键数字（费用占比、做 T 收益、止损次数等）

---

## Acceptance

1. 同一 Replay 包重复回放，关键成交与风控事件一致。
2. 可单独回放某日 Prompt 与 Decision，并查看 Memory 引用、Feature、confidence。
3. 费用估算验收：股价约 2 元时，100 股往返费用约 **10.1 元**（含双边最低佣金），而非按纯费率约 0.15 元。

---

# Chapter 11 Configuration（配置中心）

## Objective

所有参数统一管理；**禁止硬编码**关键业务阈值。

## Scope

LLM / Prompt / Risk / Trading / Scheduler / Memory / Feature / 日志 / 数据库 / Broker / 环境变量。

---

## 关键配置项（继承并扩展基线）

| 配置项 | 示例 | 说明 |
| :--- | :--- | :--- |
| `enable_deep_stop_loss` | `false` | 深度止损加速 |
| `max_liquidation_attempts` | `30` | 清仓重试（跨日累计） |
| `stale_quote_threshold_sec` | `5` | 陈旧行情阈值 |
| `max_liquidation_shares_per_tick` | 可配 | 清仓拆单 |
| `enforce_intraday_buy_limit` | `false` | 做 T 回转约束 |
| `reserved_min_cash_ratio` | `0.20` | 现金预留 |
| `max_single_position_ratio` | `0.50` | 单票上限 |
| `stop_loss_ratio` | `0.92` | 止损系数 |
| `day_loss_halt_ratio` | `0.03` | 日亏熔断 |
| `realized_loss_halt_abs` | `500` | 已实现亏损熔断 |
| `max_drawdown_liquidate` | `0.10` | 强平回撤 |
| `watchlist_limit` | `20` | 股票池上限 |
| `llm_timeout_ms` | 可配 | 决策超时 |
| `memory_top_k` | `8` | Memory 检索 |
| `decision_confidence_threshold` | `0.60` | 低于此值的 BUY/SELL 自动 HOLD |
| `regime_high_vol_max_trades_hint` | 可配 | HIGH_VOL 下做 T 频率上限 |

---

## 配置原则

1. 环境变量只放密钥与环境标识。
2. 业务参数进配置文件，变更可审计。
3. Prompt 版本与模型名可配置且可回滚。

---

## Acceptance

无业务魔法数散落代码；修改止损比例无需改代码逻辑。

---

# Chapter 12 Deployment（部署）

## Objective

Linux 长期稳定运行；任何模块异常不得导致整个 Agent 不可恢复退出。

## Scope

Ubuntu、Python、Systemd、Docker（可选）、WatchDog、日志、自动恢复/重启、数据库、备份、API、模型管理、环境变量。

---

## 12.1 运行形态

- 主机：Ubuntu LTS
- 进程管理：`systemd`
- 可选：Docker 封装
- 长期常驻，交易日与非交易日均可存活（非交易日只做维护任务）

---

## 12.2 WatchDog

负责恢复：

- 程序崩溃
- 模型异常
- 行情异常
- 网络异常
- 交易模块异常

原则：隔离重启、保留账本、告警、降级（如跳过 LLM 仅维护风控与清仓）。

---

## 12.3 备份与恢复

每日日终备份：Account 快照、Memory、Config 版本、Logs、Replay 包。  
恢复演练列入验收。

---

## Exception Handling

模块异常 → 局部降级 + WatchDog；禁止静默吞错。

---

## Acceptance

1. 模拟杀死 Decision 进程后，WatchDog 恢复且账本一致。
2. 行情中断时不产生基于陈旧行情的成交。

---

# Chapter 13 Development Roadmap（开发路线）

> 原则：**保持现有总体架构，仅做局部增强，不推倒重构。**  
> **PRD 已冻结（V2.0 Final）。下一阶段重点：开始实现、持续验证、快速迭代。**

---

## 第一阶段：稳定底座（优先验证系统可长期运行）

开发顺序（风险最低）：

```text
Trading Engine
    ↓
Risk Engine（含 confidence 过滤）
    ↓
Scheduler
    ↓
Replay（含引用信息）
    ↓
Memory
    ↓
Decision（含 confidence/reason + 基础 Feature）
    ↓
Reflection（代码统计 → LLM 解释）
```

完成能力：

- 行情接入与交易日历
- 账户 / 持仓 / T+1 / 费用 / 基准（清空重建）
- 分钟级 Decision + Risk + 模拟撮合
- 自动做 T（在用户股票池内）
- 基础市场 Feature
- 日志、Replay、Linux systemd 运行

验收重点：稳定运行、风控不可绕过、Replay 可复现。

---

## 第二阶段：计划与理解

```text
Planner
    ↓
Market Understanding（含四态 Regime）
    ↓
Report（日报增强）
    ↓
Memory 优化
```

完成能力：

- Today Plan 受 Regime 约束
- Prompt 版本管理与人工 Review
- 收益分析与统计型 Reflection 深化

---

## 第三阶段：增强（按需，不提前）

```text
Market Regime 深化 / 更多基础 Feature
    ↓
新闻理解（最后）
    ↓
Research / 多 Agent
    ↓
自动 Prompt 优化（需充分人工沉淀后）
```

明确不做过早引入：

- Alpha Engine / 复杂因子工厂
- 多 Agent 协同（Bull/Bear/Judge 等）
- 自动 Prompt 进化
- 新闻主路径依赖

---

## 阶段性成功标准

| 阶段 | 成功标准 |
| :--- | :--- |
| 第一阶段 | 模拟盘可连续多交易日无人值守运行；关键验收用例通过 |
| 第二阶段 | Planner + Regime 生效；日报可完整归因；Memory 可跨日提升决策可解释性 |
| 第三阶段 | 在不破坏物理层前提下增强理解力；长期超额相对 Buy & Hold 可评估 |

---

# 全局工程规范（Engineering Standards）— V2.0 强制

## 统一模块模板

所有可独立开发的模块（实现文档与代码目录）必须采用统一模板，保证 PRD 风格与开发效率：

| 字段 | 含义 |
| :--- | :--- |
| **Purpose** | 模块解决什么问题 |
| **Input** | 输入是什么 |
| **Output** | 输出是什么 |
| **Dependencies** | 依赖哪些模块 |
| **Processing** | 处理流程 |
| **Failure Handling** | 失败如何处理 |
| **Logging** | 记什么日志 |
| **Replay** | 如何回放/审计 |

与既有 PRD 章节字段映射：

| PRD 既有字段 | 模块模板字段 |
| :--- | :--- |
| Objective | Purpose |
| Scope / Architecture | Dependencies |
| Workflow | Processing |
| Data Structure | Input / Output |
| Exception Handling | Failure Handling |
| Logging | Logging |
| Acceptance / Replay 要求 | Replay |

> Chapter 3 Context Layer 已按该模板书写，作为范例。后续模块实现文档一律按此模板拆分。

---

## Schema Version（统一版本管理）

必须统一管理并在 Replay/配置中记录：

| Schema | 示例版本 | 说明 |
| :--- | :--- | :--- |
| Feature Schema | `feature.v1` | 基础市场/账户 Feature 字段集 |
| Memory Schema | `memory.v1` | Memory 条目结构 |
| Prompt Schema | `prompt.v1` | Prompt 元数据与渲染契约 |
| Context Schema | `context.v1` | 统一 Context 结构 |
| Decision Schema | `decision.v1` | Decision JSON（含 confidence 等） |
| Replay Schema | `replay.v1` | Replay 包结构 |

升级规则：向后兼容优先；破坏性变更必须升主版本，并提供迁移/双读策略。避免未来升级困难。

---

## Prompt Version

- `Planner Prompt v1.0`
- `Decision Prompt v1.0`
- `Reflection Prompt v1.0`
- `Market Understanding Prompt v1.0`

Replay **必须**记录 Prompt Version。Prompt 升级先人工 Review，当前版本不做自动优化。

---

## Event Log

见 Chapter 9.4。所有关键系统阶段必须产生事件，便于定位系统问题。

---

# 全局开发规范（Development Rules）

所有模块必须遵守：

| 要求 | 说明 |
| :--- | :--- |
| 可编码 | 规则有公式、状态机、原因码 |
| 可 Replay | 输入输出与配置可完整还原一次交易 |
| 可测试 | 本章验收可写成自动化用例 |
| 可维护 | 配置化、模块边界清晰、统一模板 |
| 可配置 | 禁止关键阈值硬编码 |
| 可扩展 | 预留未来能力，不破坏物理层；当前不扩复杂度 |
| 可恢复 | WatchDog + 快照 |
| 可审计 | 全链路日志、Event Log、原因码 |
| 可解释 | Decision 含 thought / reason / confidence / risk_level |
| 可持续学习 | Memory + Reflection 闭环（统计客观、解释可学习） |
| Schema 可演进 | Feature/Memory/Prompt/Replay/Context 均有版本 |

---

# 核心验收标准（汇总）

1. **风控原子性**：Tick 内触发 HALT 后，本分钟 LLM 上下文为 HALT，严禁 BUY 成交。
2. **止损深度穿透回退**：无 `bid1` 且 `mark_price` 击穿 2%（开关开启）立即止损。
3. **清仓重试跨日累计**：连续跌停场景下计数跨日累计，达 30 次撤销并告警。
4. **费用估算精度**：约 2 元股价、100 股往返费用约 10.1 元（含最低佣金）。
5. **收盘挂起**：14:57 后不执行任何指令；进行中 LLM 输出丢弃。
6. **基准再平衡**：Watchlist 变更时等权基准「清空重建」。
7. **Memory 跨日**：重启后 Memory 仍可用，且可被次日计划/决策引用。
8. **Replay 可复现**：同包回放关键结果一致；可还原 Prompt/Feature/Memory/Context/Confidence/Risk/Execution/Trade。
9. **定位合规**：产品表述不为 HFT；LLM 决策必经 Risk；Risk 100% Rule。
10. **低置信度过滤**：`confidence < decision_confidence_threshold` 的主动 BUY/SELL 不得成交。
11. **Market Regime**：日级输出为 `TREND|RANGE|HIGH_VOL|LOW_VOL` 四态之一，并可约束 Planner。
12. **Reflection 统计先行**：关键数值由代码统计，与账本一致；LLM 只做解释。
13. **Context 统一注入**：Prompt 通过 Chapter 3 Context 组装，禁止无限膨胀。
14. **Event Log**：可还原当日系统里程碑时间线。
15. **Schema Version**：Feature/Memory/Prompt/Context/Decision/Replay 均有版本号并可审计。

---

# 项目最终愿景（Vision）

打造一名真正属于个人投资者的 AI 交易员。

它能够：理解市场、理解用户、理解持仓、制定计划、执行交易、控制风险、总结经验、持续成长。

最终长期稳定跑赢 Buy & Hold。

系统不是一套「自动交易脚本」，而是一名运行于 Linux Server、长期陪伴用户投资的 **Personal AI Quant Trading Agent**。

本项目关注 **Agent 成长能力**，而非 Alpha 工厂能力。

系统坚持：

- Rule 负责确定性
- LLM 负责智能
- Replay 负责成长与 Debug
- Memory 负责经验积累
- Reflection 负责持续优化

边界清晰：不做自动选股、不做高频、不做复杂因子、不做私募量化平台、不做当前版本不需要的多 Agent / Research / 新闻主路径。

---

# Final Conclusion

本 PRD（V2.0 Final）已达到：

> **可开发（Developable）**  
> **可维护（Maintainable）**  
> **可验证（Verifiable）**  
> **可成长（Evolvable）**

四项核心目标。

**建议：停止继续设计 PRD。开始开发。**

未来所有改进，均应基于真实模拟盘数据驱动，优化 Prompt / Memory / Reflection / Feature / Replay，而不是继续扩大系统复杂度。

---

**文档结束**  
**V2.0 Final — PRD Frozen. Enter Development.**  
综合评分参考（Final Review）：9.9 / 10。
