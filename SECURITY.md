# Security Policy

## Supported version

当前仅维护 `master` 上的最新版本。项目仍处于 alpha 阶段。

## Deployment guidance

- 默认只在 `127.0.0.1` 上运行。
- 如需从其他设备访问，必须设置高强度随机 `VIDEODNA_API_TOKEN`，并通过受信任的反向代理提供 TLS。
- 不要安装来源不明的插件。插件是具有当前用户完整权限的 Python 代码。
- 不要把应用数据目录、模型配置或源视频目录共享给不受信任用户。

## Reporting a vulnerability

请通过 GitHub Security Advisory 私下报告，不要在公开 Issue 中附带 API Key、源视频、利用代码或个人路径。报告应包含受影响版本、复现步骤、影响范围和建议缓解方式。

