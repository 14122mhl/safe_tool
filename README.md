# safe-tool: 从安全 CLI 到可落地 Agent

## 1. 项目当前定位
`safe-tool` 当前是一个**可配置的安全执行网关（CLI）**，核心价值是：

- 在执行 Ansible 前做安全检查（语法、主机范围、任务风险）
- 输出决策建议（风险等级、推荐动作）
- 默认走 dry-run，避免误改生产环境
- 支持配置覆盖风险规则（`config.yaml`）

这已经有工程价值，但仍属于“命令驱动工具”，还不是“目标驱动 Agent”。

---

## 2. 最终有生产力价值的目标（Final Goal）

## 构建一个「安全变更执行 Agent」

用户只需要给目标，例如：

- “安全发布 `demo.yml` 到 `dev`”
- “检查并分批执行 `playbook.yml` 到 `stage`，失败自动归因并给修复建议”

Agent 自动完成：

1. 解析目标
2. 生成执行计划
3. 调用现有检查与执行能力（inspect/check/run/debug）
4. 在高风险点触发人工确认（尤其 prod）
5. 输出可审计结果（做了什么、为什么这么做、失败怎么处理）

这个目标的生产力价值：

- 降低运维人员的命令负担与经验门槛
- 明显减少误操作（尤其全量主机、生产执行）
- 把重复性流程沉淀为标准化自动化能力

---

## 3. 短期目标（Short-term Goal，2-4 周可交付）

## 上线 Agent MVP（半自动）

在不破坏现有命令的前提下新增目标入口：

- `safe goal "安全发布 demo.yml 到 dev"`

MVP 范围：

1. 能把自然语言目标转成执行计划（结构化步骤）
2. 自动串联：`inspect -> check -> (approval) -> run -> verify`
3. 高风险或生产环境必须人工确认
4. 失败时自动调用 debug 归因并给下一步建议
5. 保存一次运行的执行记录（JSON）

MVP 产出价值：

- 你马上拥有“可用 Agent”，而不是概念展示
- 保持现有 CLI 兼容，风险可控

---

## 4. 是否必须调用 API？是否需要 RAG？

## 结论

- **短期目标（MVP）不必须调用外部 API。**
- **短期目标（MVP）不需要做 RAG。**

## 解释

1. 你现在已有规则引擎与执行能力，先做“编排 Agent”就能产生价值。
2. 目标解析和计划生成可以先用：
   - 规则模板（无模型）
   - 或本地模型（可选）
3. RAG 适用于“海量知识检索场景”，当前阶段知识域小（风险规则 + Ansible 执行流程），暂时不需要。

## 什么时候再考虑 API / RAG

- 当你需要更强自然语言理解、多项目知识统一、跨团队经验检索时再引入。
- 推荐顺序：先 Agent 编排 -> 再 LLM API -> 最后再评估 RAG。

---

## 5. 需要的技术与资源

## 5.1 技术模块

1. **编排层（新增）**
   - 状态机：`INIT -> ANALYZE -> PLAN -> APPROVAL -> EXECUTE -> VERIFY -> DONE/FAILED`
   - 负责把现有模块组装成 Agent 流程

2. **目标解析层（新增）**
   - 输入自然语言目标
   - 输出结构化任务（playbook、env、inventory、apply策略）

3. **工具抽象层（轻改）**
   - 把现有能力包装成 Tool：
     - AnalyzeTool（analysis）
     - CheckTool（checks + engine validation）
     - RunTool（engine run）
     - DebugTool（failure parser）

4. **审批与护栏层（增强）**
   - 生产环境强制确认
   - 高风险 + 全主机范围策略阻断或二次确认

5. **运行记录层（新增）**
   - 每次运行生成 trace JSON（输入、计划、命令、结果、建议）

## 5.2 人力与时间（MVP）

- 1 名 Python 工程师（主力）
- 0.5 名运维/Ansible 领域专家（规则校验）
- 2-4 周可交付 MVP

## 5.3 基础资源

- Python 3.9+
- Ansible 环境（测试 inventory）
- CI（pytest + lint）
- 用于回归的 demo playbook 集合

---

## 6. 建议的落地路径（兼容现有命令）

1. 保持 `doctor/inspect/check/run/debug/config` 不变
2. 新增 `safe goal` 命令（调用 orchestrator）
3. 新增 `safe_tool/agent/` 目录：
   - `orchestrator.py`
   - `planner.py`
   - `policy.py`
   - `trace.py`
4. 先实现无外部 API 的规则版 Planner
5. 全部通过后，再加可选 `--llm-provider` 扩展（非必需）

---

## 7. 成功验收标准（MVP）

1. 用户可以通过一句目标触发完整流程
2. 风险护栏与审批逻辑可生效（尤其 prod）
3. 失败有自动归因与建议
4. 全流程有审计记录可回放
5. 原有命令行为不回归

---

## 8. 一句话决策建议

先做“无 API、无 RAG 的 Agent MVP”，利用你现有工程能力快速拿到生产力价值；等 MVP 在真实场景跑稳后，再决定是否接入外部 LLM API 与 RAG。

---

## 9. 当前已实现的 L1 Agent

当前项目已经新增 `safe goal` 命令，作为 Agent 的目标驱动入口。

L1 版本支持两种目标理解方式：

1. 配置 DeepSeek API 后，优先调用 DeepSeek 把自然语言目标解析成结构化计划
2. API 未配置、不可用或返回异常时，自动回退到本地规则解析

L1 Agent 当前流程：

1. 解析自然语言目标
2. 生成带置信度的执行计划
3. 缺少关键字段时进入澄清门，提示候选 playbook/inventory
4. 执行静态风险分析
5. 执行 preflight checks
6. 通过审批策略后执行 dry-run 或 apply
7. 写入 trace JSON 和执行日志
8. 失败时自动解析失败任务、失败主机和 fatal 行

---

## 10. 原有 CLI 用法（继续保留）

以下命令仍然可用：

```bash
safe doctor
safe api show
safe config show
safe config init
safe inspect demo.yml
safe check demo.yml -i inventory.ini --env dev
safe run demo.yml -i inventory.ini --env dev
safe debug ansible.log
```

说明：

- `safe doctor`：检查本地依赖
- `safe inspect`：分析 playbook 风险
- `safe check`：执行预检查，不做实际变更
- `safe run`：默认 dry-run，只有加 `--apply` 才会实际执行
- `safe debug`：解析 Ansible 日志失败信息
- `safe api show/set/disable`：管理 Agent 使用的 DeepSeek API 配置
- `safe config show/init`：查看或初始化配置

---

## 11. Agent MVP 用法

### 11.0 配置 DeepSeek API

直接配置 API key：

```bash
safe api set deepseek --api-key <DEEPSEEK_API_KEY>
```

从环境变量读取 API key：

```bash
export DEEPSEEK_API_KEY=<DEEPSEEK_API_KEY>
safe api set deepseek --api-key-env DEEPSEEK_API_KEY
```

指定模型和 API 地址：

```bash
safe api set deepseek --api-key-env DEEPSEEK_API_KEY --model deepseek-chat --base-url https://api.deepseek.com
```

查看配置时会自动脱敏：

```bash
safe api show
```

禁用 API，回到本地规则解析：

```bash
safe api disable
```

### 11.1 最简单用法

```bash
safe goal "安全发布 demo.yml 到 dev" -i inventory.ini
```

这会自动执行：

1. 目标解析
2. 计划置信度评估
3. 风险分析
4. preflight check
5. dry-run 执行
6. trace 写入 `.safe-tool/runs/*.json`

### 11.2 显式指定参数

如果目标里没有写清 playbook 或环境，可以显式传参：

```bash
safe goal "安全发布" --playbook demo.yml -i inventory.ini --env dev
```

### 11.3 强制 dry-run

```bash
safe goal "发布 demo.yml 到 dev" -i inventory.ini --dry-run
```

### 11.4 非生产 apply

实际执行需要显式 approval：

```bash
safe goal "发布 demo.yml 到 dev" -i inventory.ini --apply --approve
```

### 11.5 生产 apply

生产执行需要更严格确认：

```bash
safe goal "发布 demo.yml 到 prod" -i inventory.ini --apply --approve --confirm PROD
```

如果缺少 `--approve` 或 `--confirm PROD`，Agent 会在审批门禁阶段阻断。

### 11.6 指定 trace 输出

```bash
safe goal "安全发布 demo.yml 到 dev" -i inventory.ini --trace-out run-trace.json
```

默认 trace 路径：

```text
.safe-tool/runs/<run_id>.json
```

默认执行日志路径：

```text
.safe-tool/runs/<run_id>.log
```

---

## 12. Agent MVP 的安全边界

当前 Agent MVP 的安全策略：

1. DeepSeek 只负责解析目标，不直接执行命令
2. CLI 显式参数优先级最高，可覆盖模型结果
3. 默认不直接 apply
4. apply 必须加 `--approve`
5. 低置信度计划禁止 apply，需显式补参数
6. production apply 必须额外加 `--confirm PROD`
7. preflight check 失败时直接阻断执行
8. 所有执行都会记录 trace

这使它更像一个“安全编排 Agent”，而不是简单脚本。