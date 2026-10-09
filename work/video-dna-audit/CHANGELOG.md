# Changelog

所有重要变更记录在此文件。版本格式遵循 Semantic Versioning。

## [Unreleased]

- 增加任务中心，集中展示后台分析进度、失败原因、取消入口和已完成结果。
- 支持一次选择或拖入多个视频，按顺序执行批量分析并在项目素材栏显示队列。
- 保存项目结果快照，重新打开项目时恢复镜头人工修改和复核状态。
- 导出前增加镜头重叠、空洞、帧率、最小帧数和源素材路径预检。
- 修正安全文档，明确 Electron 使用系统凭据库保存模型密钥，并标注浏览器模式边界。

## [0.4.0] - 2026-08-20

### Changed

- 后端从 Python/FastAPI/PyInstaller 迁移到 Go 1.25 + go-zero，UI 内嵌到单个后端可执行文件。
- API 使用 goctl 契约生成 handler/logic/types 骨架，并按 handler、logic、service、`pkg/x*` 分层。
- 视频分析改为 FFmpeg/FFprobe 外部工具 + 纯 Go 音频节奏与图像启发式，不依赖 CGO。
- 插件协议改为跨平台可执行文件的 JSON stdin/stdout 协议。
- GitHub Actions 改为 Go 测试、交叉编译和 Electron 安装包流程。

### Added

- Windows FFmpeg 自动下载、SHA-256 校验和安装包内置流程。
- Go 导出、模板、存储、任务状态回归测试。
- 可直接从 macOS/Linux/Windows 交叉编译的 Windows `backend.exe`。

### Removed

- Python 服务、虚拟环境依赖、PyInstaller 配置和 Python 测试链。

## [0.3.1] - 2026-08-20

### Changed

- 后端按 `core`、`services`、`api/routes` 分层，入口改为应用工厂。
- 前端从单文件拆为 HTML、CSS 和 JavaScript 静态资源。
- 使用平台规范的用户数据目录，并支持 `VIDEODNA_DATA_DIR`。
- API Key 改为请求级显式传递，模型列表不再返回明文密钥。
- Electron 原生文件选择改为流式 multipart 上传。

### Fixed

- 修复历史容量清理可能连续误删的问题。
- 修复高密度模板在短视频上产生越界和负时长的问题。
- 修复 EDL 转场固定写为硬切的问题。
- 修复 SRT 时间戳产生 `1000` 毫秒的问题。
- FCP7 XML 改为引用源视频素材。

## [0.3.0] - 2026-08-20

- 增加历史回看、后台进度、剪映草稿、AI 创作中心和主题设置。

## [0.2.0]

- 初始公开版本，包含分析管线、CLI、Web UI 和 Electron 壳。
