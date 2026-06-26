# safe-tool

`safe-tool` 是一个面向 Ansible 兼容运维流程的安全执行网关。它在真正执行变更前提供静态风险分析、预检查、dry-run、生产环境护栏、失败日志归因和可审计 trace，目标是把高风险命令式操作收敛成更稳的安全变更流程。

当前版本已经包含 L1 Agent：可以通过 `safe goal "安全发布 demo.yml 到 dev"` 这类自然语言目标触发完整流程。DeepSeek API 可选；未配置或调用失败时会自动回退到本地规则解析。

## 目录

- [核心能力](#核心能力)
- [安装](#安装)
- [快速开始](#快速开始)
- [命令总览](#命令总览)
- [全局参数](#全局参数)
- [Playbook 命令](#playbook-命令)
- [Agent 命令](#agent-命令)
- [API 配置命令](#api-配置命令)
- [配置命令](#配置命令)
- [配置文件](#配置文件)
- [Agent 工作流](#agent-工作流)
- [安全策略](#安全策略)
- [项目结构](#项目结构)
- [开发与测试](#开发与测试)

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 静态风险分析 | 解析 playbook 任务、模块、主机范围，并输出风险等级与建议 |
| 预检查 | 检查 playbook、inventory、env、Ansible syntax、host list、task list |
| 默认 dry-run | `safe run` 和 `safe goal` 默认避免真实变更，执行前先展示命令 |
| 生产护栏 | `prod/production` apply 必须显式确认 `--confirm PROD` |
| Agent 编排 | `safe goal` 将自然语言目标转为计划并串联分析、检查、审批、执行、验证 |
| DeepSeek 解析 | 可选使用 DeepSeek 解析目标；失败时回退到本地规则 |
| 失败归因 | 执行失败后解析 failed task、failed host 和 fatal 行 |
| 审计 trace | Agent 运行写入 `.safe-tool/runs/<run_id>.json` 和对应日志 |

## 安装

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 本地开发安装 | `python3 -m pip install -e .` | 安装 `safe` 命令入口 |
| 安装依赖 | `python3 -m pip install PyYAML pytest` | 适合未使用 editable install 的环境 |
| 检查环境 | `python3 safe.py doctor` | 检查 Python、Ansible、PyYAML |

运行 Ansible 校验或执行前，建议确保 `ansible-playbook` 已在 `PATH` 中。未安装 Ansible 时，部分检查会以 WARN 形式跳过。

## 快速开始

| 目标 | 命令 |
| --- | --- |
| 检查本地环境 | `safe doctor` |
| 查看 playbook 风险 | `safe inspect demo.yml` |
| 执行预检查 | `safe check demo.yml -i inventory.ini --env dev` |
| dry-run 执行 | `safe run demo.yml -i inventory.ini --env dev` |
| 用 Agent 执行安全发布流程 | `safe goal "安全发布 demo.yml 到 dev" -i inventory.ini` |
| 非生产真实执行 | `safe goal "发布 demo.yml 到 dev" -i inventory.ini --apply --approve` |
| 生产真实执行 | `safe goal "发布 demo.yml 到 prod" -i inventory.ini --apply --approve --confirm PROD` |

## 命令总览

| 命令 | 用途 | 是否执行变更 |
| --- | --- | --- |
| `safe doctor` | 检查本地依赖和工具链 | 否 |
| `safe inspect <playbook>` | 分析 playbook 结构、任务模块和风险 | 否 |
| `safe check <playbook>` | 执行安全预检查 | 否 |
| `safe run <playbook>` | 预检查后 dry-run 或 apply | 默认否，带 `--apply` 是 |
| `safe debug <logfile>` | 解析 Ansible 输出或日志中的失败信息 | 否 |
| `safe goal <goal...>` | 从自然语言目标运行 Agent 工作流 | 默认否，带 `--apply --approve` 可执行 |
| `safe api set/show/disable` | 管理 DeepSeek API 配置 | 否 |
| `safe config show/init` | 查看或初始化配置文件 | 否 |

## 全局参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--engine <engine>` | `SAFE_ENGINE` 或 `ansible` | Ansible 执行器；可传命令名或路径 |
| `--config <path>` | `./config.yaml` | 指定配置文件路径 |

## Playbook 命令

### `safe inspect`

| 用法 | 说明 |
| --- | --- |
| `safe inspect <playbook>` | 只做静态分析，输出整体风险、任务风险和建议 |

### `safe check`

| 用法 | 说明 |
| --- | --- |
| `safe check <playbook> [options]` | 执行 playbook 存在性、inventory、env、风险扫描和 Ansible 预检查 |

| 参数 | 是否必需 | 说明 |
| --- | --- | --- |
| `<playbook>` | 是 | playbook 文件路径 |
| `-i, --inventory <path>` | 否 | inventory 文件或路径 |
| `--limit <pattern>` | 否 | 限制目标主机范围 |
| `--env <env>` | 否 | 环境名，支持 `dev/test/stage/staging/prod/production` |
| `-e, --extra-var <value>` | 否 | 额外变量，可重复传入 |
| `--report <path>` | 否 | 写入 JSON 检查报告 |

### `safe run`

| 用法 | 说明 |
| --- | --- |
| `safe run <playbook> [options]` | 先执行 `check`，通过后进入 dry-run 或 apply |

| 参数 | 是否必需 | 说明 |
| --- | --- | --- |
| `<playbook>` | 是 | playbook 文件路径 |
| `-i, --inventory <path>` | 否 | inventory 文件或路径 |
| `--limit <pattern>` | 否 | 限制目标主机范围 |
| `--env <env>` | 否 | 环境名 |
| `-e, --extra-var <value>` | 否 | 额外变量，可重复传入 |
| `--report <path>` | 否 | 写入 JSON 检查报告 |
| `--apply` | 否 | 真实执行变更；不传时为 dry-run |
| `--confirm PROD` | 生产 apply 必需 | 对 `prod/production` 真实执行的二次确认 |
| `--timeout <seconds>` | 否 | 执行超时时间，默认 `600` |

### `safe debug`

| 用法 | 说明 |
| --- | --- |
| `safe debug <logfile>` | 解析 Ansible 日志，输出 failed tasks、failed hosts 和 fatal lines |

## Agent 命令

### `safe goal`

| 用法 | 说明 |
| --- | --- |
| `safe goal <goal...> [options]` | 从自然语言目标生成计划，并运行 Agent 安全执行流程 |

| 参数 | 是否必需 | 说明 |
| --- | --- | --- |
| `<goal...>` | 是 | 自然语言目标，例如 `"安全发布 demo.yml 到 dev"` |
| `--playbook <path>` | 否 | 显式指定 playbook，优先级高于目标解析 |
| `-i, --inventory <path>` | 否 | inventory 文件或路径 |
| `--limit <pattern>` | 否 | 限制目标主机范围 |
| `--env <env>` | 否 | 显式指定环境，优先级高于目标解析 |
| `-e, --extra-var <value>` | 否 | 额外变量，可重复传入 |
| `--apply` | 否 | 允许 Agent 进入真实执行模式 |
| `--dry-run` | 否 | 强制 dry-run |
| `--approve` | apply 必需 | 明确批准非生产真实执行 |
| `--confirm PROD` | 生产 apply 必需 | 明确批准生产真实执行 |
| `--timeout <seconds>` | 否 | 执行超时时间，默认 `600` |
| `--report <path>` | 否 | 写入 JSON 检查报告 |
| `--trace-out <path>` | 否 | 指定 Agent trace 输出路径 |

| 示例 | 说明 |
| --- | --- |
| `safe goal "安全发布 demo.yml 到 dev" -i inventory.ini` | 自动解析目标并执行 dry-run 流程 |
| `safe goal "安全发布" --playbook demo.yml -i inventory.ini --env dev` | 用显式参数补齐目标 |
| `safe goal "发布 demo.yml 到 dev" -i inventory.ini --dry-run` | 强制 dry-run |
| `safe goal "发布 demo.yml 到 dev" -i inventory.ini --apply --approve` | 非生产真实执行 |
| `safe goal "发布 demo.yml 到 prod" -i inventory.ini --apply --approve --confirm PROD` | 生产真实执行 |
| `safe goal "安全发布 demo.yml 到 dev" -i inventory.ini --trace-out run-trace.json` | 指定 trace 文件 |

## API 配置命令

DeepSeek API 只用于目标解析，不直接执行命令。CLI 显式参数优先级始终高于模型解析结果。

| 命令 | 说明 |
| --- | --- |
| `safe api set deepseek --api-key <DEEPSEEK_API_KEY>` | 直接写入 DeepSeek API key |
| `safe api set deepseek --api-key-env DEEPSEEK_API_KEY` | 从环境变量读取 API key 并写入配置 |
| `safe api set deepseek --api-key-env DEEPSEEK_API_KEY --model deepseek-chat --base-url https://api.deepseek.com` | 指定模型和 API 地址 |
| `safe api show` | 查看 API 配置，密钥自动脱敏 |
| `safe api disable` | 禁用 API，回到本地规则解析 |

| `api set` 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `provider` | 无 | 当前支持 `deepseek` |
| `--api-key <key>` | 无 | 直接传入 API key |
| `--api-key-env <name>` | 无 | 从环境变量读取 API key |
| `--base-url <url>` | `https://api.deepseek.com` | DeepSeek 兼容 API 地址 |
| `--model <name>` | `deepseek-chat` | 模型名称 |
| `--timeout <seconds>` | `30` | API 请求超时时间 |

## 配置命令

| 命令 | 说明 |
| --- | --- |
| `safe config show` | 打印有效配置，密钥字段会脱敏 |
| `safe config init` | 在当前目录写入默认 `config.yaml`；已存在时不覆盖 |

## 配置文件

默认配置文件为当前目录的 `config.yaml`。可以通过 `--config <path>` 指定其他路径。

| 配置段 | 用途 |
| --- | --- |
| `risk_rules` | 覆盖或扩展模块风险等级、原因和建议 |
| `settings.default_engine` | 默认执行器 |
| `settings.default_env` | 目标未指定环境时的默认环境 |
| `settings.require_prod_confirm` | 是否要求生产 apply 使用 `--confirm PROD` |
| `settings.dry_run_by_default` | 默认 dry-run 策略 |
| `settings.min_goal_confidence_to_apply` | Agent apply 的最低计划置信度 |
| `api.provider` | 当前 API provider，未启用时为 `null` |
| `api.deepseek` | DeepSeek 配置 |

## Agent 工作流

| 阶段 | 行为 | 失败处理 |
| --- | --- | --- |
| Plan | 解析目标，合并 CLI 显式参数、DeepSeek hints 和本地规则 | 缺少 playbook 等关键字段时进入澄清门 |
| Analyze | 静态分析 playbook 风险 | 分析失败则终止 |
| Check | 执行预检查和 Ansible 校验 | FAIL 时阻断执行 |
| Approval | 根据 env、risk、confidence、approve、confirm 判断是否放行 | 不满足门禁则终止 |
| Execute | dry-run 或 apply 执行 Ansible 命令 | 写入运行日志 |
| Verify | 成功时写 trace；失败时解析日志归因 | 输出 failed task、failed host 和 fatal line |

默认 trace 路径为 `.safe-tool/runs/<run_id>.json`，默认执行日志路径为 `.safe-tool/runs/<run_id>.log`。

## 安全策略

| 策略 | 说明 |
| --- | --- |
| 默认不 apply | 未显式传 `--apply` 时执行 dry-run |
| apply 必须批准 | `safe goal --apply` 还必须传 `--approve` |
| 生产二次确认 | `prod/production` apply 必须传 `--confirm PROD` |
| CLI 参数优先 | `--playbook`、`--env`、`--inventory` 等显式参数覆盖模型结果 |
| 低置信度阻断 | Agent 计划置信度低于阈值时禁止 apply |
| 检查失败阻断 | preflight check 出现 FAIL 时不执行后续步骤 |
| API 不执行命令 | DeepSeek 只返回结构化目标 hints，不接触执行器 |
| 全流程审计 | Agent 每次运行写入 trace 和日志 |

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `safe.py` | 兼容入口，调用 `safe_tool.cli:main` |
| `safe_tool/cli.py` | argparse 命令定义 |
| `safe_tool/commands.py` | CLI 命令实现 |
| `safe_tool/analysis.py` | playbook 风险分析和失败日志解析 |
| `safe_tool/checks.py` | 本地检查和生产环境 guard |
| `safe_tool/config.py` | 配置加载、合并、写入和脱敏 |
| `safe_tool/engine.py` | Ansible 命令构造、执行和校验 |
| `safe_tool/models.py` | 数据模型 |
| `safe_tool/output.py` | 终端输出和 JSON report |
| `safe_tool/agent/planner.py` | 本地目标解析与计划生成 |
| `safe_tool/agent/deepseek.py` | DeepSeek 目标解析客户端 |
| `safe_tool/agent/policy.py` | Agent 审批策略 |
| `safe_tool/agent/orchestrator.py` | Agent 工作流编排 |
| `safe_tool/agent/trace.py` | run id、trace 和日志路径 |
| `tests/` | 单元测试 |
| `demo.yml` | 示例 playbook |
| `inventory.ini` | 示例 inventory |
| `config.yaml` | 示例配置 |

## 开发与测试

| 任务 | 命令 |
| --- | --- |
| 运行测试 | `python3 -m pytest` |
| 运行入口脚本 | `python3 safe.py doctor` |
| 查看 CLI 帮助 | `python3 safe.py --help` |
| 查看 Agent 帮助 | `python3 safe.py goal --help` |

当前测试覆盖配置、CLI、Agent planner、审批策略、风险分析和基础检查。