# Target-driven design (开局取舍 / 权衡 / 反激进)

设计开局**先排目标优先级**（时序 / 面积 / 功耗 选一个为主，其他作约束）。
每个优化都要**算账** —— 收益与代价不匹配就别做。"为了优化而优化"是
这一节明确反对的。

## 主目标排序

每个项目挑 **一个** 主目标，其余作 hard constraint。三选一选错并不致命，
但"三个都想要"会让每个都做成半吊子。

| 主目标 | spec 阶段必须决（不可逆 / 贵） | 其余作约束 |
|---|---|---|
| 时序 (Fmax) | 时钟方案、接口流水线深度、跨域 CDC 模式 | 面积 ≤ X、功耗 ≤ Y |
| 面积 | 资源共享策略、内存映射策略、参数化删减 | Fmax ≥ X、功耗 ≤ Y |
| 功耗 | 时钟门控策略、内存 enable、是否多电压域、是否 retention | Fmax ≥ X、面积 ≤ Y |

`hardware-design-planning` brainstorm Q3 (Primary risk) + Q4 (Hard constraints)
正是用来把这个排序压在 spec 里的。

## 时序优化 — 划算 / 过激

✅ 划算：
- 对 **measured** critical path 加 1 级 pipeline，换显著 Fmax 提升
- balance adder / mux / reduction 树（资源不变 → 免费）
- 让 synth 做 retiming（一行 directive）
- 修 missing / wrong clock constraint（最便宜，先做）
- 复制高 fanout register 降扇出

❌ 过激信号：
- 不看 critical path 就给整个 datapath 加 pipeline
- 每个 module 边界都塞 register slice "防御"，下游协议承受不起延迟
- 单次改动收益小（几个 % Fmax）却新增 ≥ 1 级流水
- 把 1 cycle 接口拉到 N cycle，但 spec 没说支持这种延迟
- 用 over-encoded one-hot FSM 换 Fmax，但 FF 涨数倍

## 面积优化 — 划算 / 过激

✅ 划算：
- 共享真正昂贵的资源（multiplier / divider / 大 adder），且 throughput 允许
- right-size datapath 宽度（去掉精度无用 bit）
- 删冗余 decode / dead logic（免费）
- BRAM 替代分布式 RAM（如果 BRAM 还有富余）

❌ 过激信号：
- 8-state 调度 FSM 共享 1 个 multiplier，省 9 DSP 换 200 LUT control + Fmax 损失
- highly encoded FSM 省 1 FF 换 显著 Fmax 损失
- 共享后破坏接口 throughput 契约
- 删 parameter "灵活性"，导致以后改动要 rewrite 整模块

## 功耗优化 — 划算 / 过激

✅ 划算：
- clock enable 替代手搓 gated clock（基本免费）
- DSP operand isolation（免费）
- BRAM / SRAM read enable，空闲时不取
- valid / enable guards 避免 glitchy combinational toggle
- 用 vendor ICG (integrated clock gating) primitive

❌ 过激信号：
- 引入多电压域 → 强制加 retention FF + bus isolator + power sequencer，
  验证成本和 sign-off 复杂度翻倍
- 手搓 clock gating cell（不用 vendor primitive）→ STA / GLS 出问题
- 改造 free-running counter 成事件驱动，但收益小却引入新时钟域
- 为了功耗把时钟降到无法满足 throughput 目标

## 权衡通用三问（每个优化前问自己）

1. **针对 measured bottleneck 吗？** —— 不是测出来的就别动；凭感觉优化最烧时间。
2. **总代价 < 收益吗？** —— 列出：latency、面积、功耗、验证复杂度、接口契约影响。
   任一项不可接受就放弃。
3. **可逆吗？** —— spec 级决策（电压域 / 时钟方案）几乎改不回；RTL 级能改但贵；
   implementation 级 directive 便宜。**先用最便宜的修法**。

## 阶段-决策地图（先用便宜的）

| 阶段 | 决策类 | 改动成本 |
|---|---|---|
| **spec** | 主目标排序、时钟方案、电压域、内存策略、接口流水线策略 | 不可逆 / 极贵 |
| **RTL** | 流水线深度、FSM 编码、资源共享布置、clock enable 布置 | 中等（rewrite 模块） |
| **Synthesis** | retiming / FSM 重映射 / opt 指令 | 便宜（改 tcl） |
| **pnr** | floorplan / pblock / placement 引导 | 便宜，但边际效益 |

**规则**：要解决一个问题，**从最便宜的阶段开始试**。pnr 加 pblock 能解决就别动 RTL；
RTL 改一个 enable 能解决就别动 spec。
