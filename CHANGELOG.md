# 更新日志

## [Unreleased]

## 0.2.0 - 2026-08-19

### 变更

- 发布管理页重试、超时与移动端交互优化。

### 修复

- 管理页补齐 Bridge/API 超时、可重试初始化、旧错误清理、键盘焦点和移动端布局反馈。

## 0.1.1 - 2026-07-27

### 修复

- 在 `metadata.yaml` 声明 `repo` 与 `homepage`，使 AstrBot 能定位仓库并执行后续在线更新。
- 修正 Plugin Page 对 AstrBot 页面通信桥的探测与 `apiGet()` 调用方式。
- 稳定热重载后的当前中枢实例与注册表发现，避免页面继续引用已卸载实例。
- 补充 README 和更新日志，确保插件管理页能够展示说明与版本变更。

## 0.1.0 - 2026-07-27

### 新增

- 新增标准模型 `CapabilityDescriptor`、`CallContext` 与 `ServiceResponse`。
- 新增能力注册、注销、发现、重复注册、热替换及租约失效。
- 新增合同版本与 JSON Schema 校验、deadline、并发限制、标准错误码和 trace_id。
- 新增 `/hub status`、`/hub services` 与 `/hub diagnose` 管理命令。
- 新增 Plugin Page 能力探测和不可用时的核心功能降级。
- 新增脱敏注册表快照与审计日志，默认不记录 payload。
- 新增正常与异常调用、热重载和 `terminate()` 清理测试。
## [Unreleased]

### 修复

- 管理页补齐 Bridge/API 超时、可重试初始化、旧错误清理、键盘焦点和移动端布局反馈。
