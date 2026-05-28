# LogicPilot

> 面向前端 RTL / FPGA / ASIC 设计流程的 AI 代理插件，适用于 Claude Code 与 Codex。

**License:** MIT | **Python:** 3.10+（3.10 需 `pip install tomli`）| **平台:** Linux · macOS · Windows

---

## 简介

LogicPilot 不是 RTL 生成器，也不绑定某一家 EDA 厂商。

它把硬件前端流程中最容易出错的环节——设计规划、静态检查、仿真、综合、CDC、功耗——包装成 AI 代理可读的 JSON 契约，让 Claude Code / Codex 像跑 CI 一样跑硬件流程。每个阶段的结果由 Python 驱动器生成，AI 只能读取结果，不能自行宣布通过。

**不包含：** DFT/ATPG、后端布线（PnR 作为可选透传）、IP 集成、GDS 签核。

---

## 流程

```
规格说明 → 微架构 → RTL 编写 → 源码审查 → TB 审查 → Lint → 仿真 → 综合 → [后端] → 报告
             ↑                      ↑             ↑              ↑           ↑
         hardware-design-planning  audit       tb-audit        sim         synth
```

默认前端流水线（Claude Code 中为 `/lp-front`；Codex fallback prompt 中为 `/lp-run all`）：

```
plan-check → audit → tb-audit → lint → sim → synth → report
```

每个阶段输出 JSON。常规 stage `status` 使用 `pass / fail / blocked / skipped / timeout / dry-run`；`/lp-doctor` 的单项检查还会使用 `warn`。流水线在第一个非 pass 处停止并标注原因。

---

## 功能

| 功能 | Claude Code 命令 | Codex fallback prompt | 说明 |
|---|---|---|---|
| 项目初始化 | `/lp-init` | `/lp-init` | 生成 `flow.toml` 和规划文档模板 |
| 环境诊断 | `/lp-doctor` | `/lp-doctor` | 检查 Python 版本、配置、工具可用性 |
| 前端流水线 | `/lp-front` | `/lp-run all` | 串联 plan-check → audit → tb-audit → lint → sim → synth → report |
| RTL 静态审查 | `/lp-audit` | `/lp-run audit` | 无需外部 EDA；检测 latch、multi-driver、不可综合构造等 |
| TB 审查 | `/lp-tb` | `/lp-run tb-audit` | 检测仅有波形无自检、缺少 PASS/FAIL 标记、随机测试无种子记录等 |
| Lint | `/lp-lint` | `/lp-run lint` | 调用 verilator / verible / ghdl |
| 仿真 | `/lp-sim` | `/lp-sim` | 调用 verilator / iverilog / ghdl / questa 等 |
| 综合 | `/lp-synth` | `/lp-run synth` | 调用 yosys / vivado / quartus / openroad 等 |
| CDC 检查 | `/lp-cdc-check` | `/lp-cdc-check` | SpyGlass CDC 优先，降级为 verilator `--cdc`；单时钟设计自动跳过 |
| 形式验证 | `/lp-formal` | `/lp-formal` | 调用 sby / jaspergold / vcf / qverify |
| 功耗分析 | `/lp-power` | `/lp-power` | VCD → SAIF → 功耗报告，必须注明活动率假设 |
| 时序约束生成 | `/lp-constraints` | `/lp-constraints` | 生成 SDC/XDC 约束模板 |
| 综合报告解读 | `synth-report-reader` 子代理 | `hardware-synthesis` skill | 解析大型综合日志，提取 WNS/TNS/利用率/结构性 warning |
| 结果分诊 | `logicpilot-result-triage` skill | `logicpilot-result-triage` skill | 把 JSON 输出归纳为 verdict → cause → next action |

**硬性门控（完成前必须满足）：**

- **规划门控**：新模块必须先通过 `plan-check`，再写 RTL。
- **CDC 门控**：有 ≥2 个无关时钟的设计，CDC 检查未通过不能声明完成。
- **纪律门控**：每次 RTL 修改前须应用 `hardware-design-discipline`。

---

## Skill 清单

| Skill | 用途 |
|---|---|
| `hardware-design-planning` | 规格、微架构、任务分解 |
| `hardware-design-discipline` | RTL 修改前的假设梳理与目标定义 |
| `hardware-rtl-design` | RTL 编写与审查 |
| `hardware-rtl-audit` | 源码风险扫描（不依赖 EDA 工具） |
| `hardware-synthesizable-coding` | 可综合编码规范 |
| `hardware-reset-design` | 复位架构与复位域交叉 |
| `hardware-fsm-design` | 状态机设计与编码 |
| `hardware-cdc` | 时钟域与复位域交叉结构审查 |
| `hardware-constraints` | SDC/XDC 时序约束 |
| `hardware-interfaces` | AXI / APB / AHB / Wishbone 等接口 |
| `hardware-simulation` | 仿真调试 |
| `hardware-verification` | 验证规划、TB 架构、覆盖率 |
| `hardware-synthesis` | 综合报告解读 |
| `hardware-power-analysis` | 功耗估算与预算 |
| `systemverilog-design-modeling` | SV package / interface / typedef |
| `systemverilog-verification-platform` | SV TB 平台架构 |
| `fpga-architecture-optimization` | FPGA RTL 层优化 |
| `fpga-timing-closure` | FPGA 时序收敛迭代 |
| `logicpilot-result-triage` | LogicPilot JSON 结果分诊 |

---

## 安装

### Claude Code

```
/plugin marketplace add shijhtop/LogicPilot
/plugin install logicpilot@logicpilot-marketplace
```

### Codex

打开 `/plugins` → **Add marketplace** → 输入 `shijhtop/LogicPilot` → 安装 **LogicPilot**。

---

## 开发者

`shared/flow` 是流程驱动唯一源码，`shared/skills` 是技能唯一源码。`claude-code/plugins/logicpilot/` 为平台包（从 `shared/` 同步生成）。

```bash
# 运行测试
python3 -m pytest shared/flow/tests -q
python3 -m pytest shared/skill_tests -q
```

快速验证：

```bash
python3 shared/flow/logicpilot.py --doctor --config flow.toml
python3 shared/flow/logicpilot.py --list --config flow.toml
python3 shared/flow/logicpilot.py all --config flow.toml
```

English version: [README.en.md](README.en.md)

---

## 免责声明

本项目以 **MIT 许可证**开源，按"现状"提供，不附带任何明示或暗示的保证。

- **设计正确性**：LogicPilot 是辅助工具，不替代工程师判断。`status: pass` 不等同于设计无误，更不等同于可流片（tape-out）级别的 sign-off。CDC 检查、时序分析、功耗估算的结果均依赖工具输出和用户提供的配置，其准确性由所用 EDA 工具及配置质量决定。
- **EDA 工具**：本插件调用的第三方 EDA 工具（Yosys、Verilator、Vivado、SpyGlass 等）均有各自的许可证和使用条款，用户须自行确保合规使用。
- **商业工具**：SpyGlass、JasperGold、Questa 等商业工具需要有效许可证，本项目不提供也不担保对这些工具的访问权。
- **AI 输出**：本插件依赖大语言模型（Claude）进行分析和建议，AI 输出可能存在错误、遗漏或幻觉，关键设计决策须经有资质的工程师审查。
- **损失责任**：在适用法律允许的最大范围内，作者不对因使用本软件导致的任何直接或间接损失（包括但不限于流片失败、设计缺陷、知识产权纠纷）承担责任。
