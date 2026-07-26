# 凝心溯溪-枢（astrbot_plugin_orchestration_hub）

凝心溯溪系列服务中枢模块：为同一 AstrBot 进程内的插件提供显式、可版本化的能力注册、服务发现、调用治理、事件传递与任务编排基础设施。

当前版本只实现第一阶段注册与调用治理，不复制“知、言、序、情、声、核”的领域逻辑，不读取其他插件私有数据库，不依赖其他插件私有属性，也不接管 AstrBot 全局 Hook。

## 当前版本

- 插件版本：`0.1.0`
- AstrBot 兼容范围：`>=4.16,<5`
- 展示名：`凝心溯溪-枢`
- 仓库：https://github.com/qsbb/astrbot_plugin_orchestration_hub

## 第一阶段能力

- 标准模型：`CapabilityDescriptor`、`CallContext`、`ServiceResponse`。
- 能力注册表：注册、注销、发现、重复注册、热替换、租约续期与失效。
- 调用治理：合同版本检查、JSON Schema 输入输出校验、deadline、并发限制、标准错误码和 `trace_id`。
- 管理命令：`/hub status`、`/hub services`、`/hub diagnose`。
- Plugin Page：展示服务数量、实例数量、注册表版本、已注册服务和近期调用。
- 数据持久化：在 AstrBot data 目录写入脱敏的 `registry_snapshot.json` 与 `audit.jsonl`，默认不记录 payload。
- 生命周期：`terminate()` 停止注册、等待在途调用、取消租约任务并清理缓存和注册表。

## 安装

将插件目录放入 AstrBot 的 `data/plugins/` 或运行环境对应的插件目录，也可通过 AstrBot 插件管理页面使用仓库地址安装：

```text
https://github.com/qsbb/astrbot_plugin_orchestration_hub
```

安装或更新后重载插件。

## 管理命令

| 命令 | 说明 |
|---|---|
| `/hub status` | 查看服务、实例、注册表版本和页面能力状态 |
| `/hub services` | 查看当前已注册服务 |
| `/hub diagnose` | 查看 Page API 和注册表运行状态 |

## Plugin Page

在支持 Plugin Page 的 AstrBot 版本中，可从插件详情打开“服务中枢”页面。页面通过运行时能力探测注册管理 API；页面能力不可用时，注册、发现、调用和命令仍可正常工作。

## 数据与隐私

运行数据仅写入 AstrBot 为插件提供的 data 目录：

- `registry_snapshot.json`：脱敏注册表快照。
- `audit.jsonl`：脱敏审计事件。

默认不持久化调用 payload；名称包含 `payload`、`content`、`message`、`prompt`、`token`、`secret`、`password` 等敏感标记的字段会被删除或脱敏。

## 开发验证

在插件目录运行：

```text
python -m pytest -q
python -m ruff check .
python -m py_compile main.py pages_manager.py core/*.py adapters/*.py
node --check pages/manager/app.js
```

## 范围限制

第一阶段不实现外部 HTTP 服务、多实例消息队列、跨进程服务发现或通用可视化工作流。跨插件接入只应依赖公开契约，不应访问其他插件私有数据库或私有属性。
