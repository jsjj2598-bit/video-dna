# Video DNA Analyzer

本地优先的视频剪辑结构分析桌面应用。后端自 `v0.4.0` 起使用 Go + go-zero，前端保留 Electron 桌面壳；一个 Go 可执行文件内嵌 UI，运行时只依赖 FFmpeg/FFprobe，不再需要 Python、虚拟环境或 PyInstaller。

## 能力

- FFprobe 元信息、FFmpeg 场景分数镜头切分与关键帧提取
- 纯 Go 流式音频能量、瞬态、BPM、节拍和静音区间分析
- 纯 Go 关键帧亮度/色彩/细节启发式描述，可选 OpenAI 兼容视觉模型
- 分析历史、Range 视频回放、任务进度与本地容量清理
- EDL、FCP7 XML、Cutmark JSON、SRT、ZIP 和剪映草稿导出
- 模型、组件、技能和跨平台可执行插件注册
- Windows/macOS Electron 安装包与 Windows 后端交叉编译

## 快速开始

需要 Go 1.25、Node.js 20+、FFmpeg 和 FFprobe。

```bash
npm ci
npm start
```

`npm start` 会先构建当前平台的 `dist/backend`（Windows 为 `backend.exe`），再打开 Electron 窗口。开发后端可单独启动：

```bash
go run ./service/videodna/api -f service/videodna/api/etc/videodna.yaml
```

浏览器访问 `http://127.0.0.1:8000` 只是调试方式；正式使用入口是 Electron 桌面窗口。UI 由 Go 可执行文件内嵌并通过本机 HTTP 提供，不是部署到公网的网站。

## 构建

```bash
# 当前平台的独立 Go 后端
npm run build:backend

# 在 macOS/Linux/Windows 上交叉编译 64 位 Windows 后端
npm run build:backend:win

# 完整 Windows 安装包/便携版；自动下载固定版静态 FFmpeg/FFprobe、校验 SHA-256
npm run package:win

# 当前 Mac 或 Linux 安装包
npm run package:mac
npm run package:linux
```

Windows FFmpeg/FFprobe 固定使用 [ffmpeg-static b6.1.1](https://github.com/eugeneware/ffmpeg-static/releases/tag/b6.1.1) 发布物。构建脚本校验仓库固定的 SHA-256，把工具放到 `dist/tools`，Electron 再打进 `resources/tools`；首次下载后存入用户缓存。

> Windows 的 Go 后端可以在任意系统直接交叉编译。Electron 的完整 Windows 安装器通常也可跨平台生成，但遇到签名、NSIS 或平台工具限制时，使用仓库的 `Build Installers` GitHub Actions 最稳定。

## 配置

默认配置见 `service/videodna/api/etc/videodna.yaml`。独立可执行文件找不到 YAML 时会使用安全的桌面默认值。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VIDEODNA_HOST` | `127.0.0.1` | 监听地址 |
| `VIDEODNA_PORT` | `8000` | 本机端口 |
| `VIDEODNA_DATA_DIR` | 平台用户数据目录 | 配置、插件、历史与下载目录 |
| `VIDEODNA_API_TOKEN` | 空 | 非空时保护所有 `/api` 接口 |
| `VIDEODNA_FFMPEG` | 自动发现 | FFmpeg 可执行文件路径 |
| `VIDEODNA_FFPROBE` | 自动发现 | FFprobe 可执行文件路径 |

数据目录：

- macOS：`~/Library/Application Support/Video DNA Analyzer`
- Windows：`%LOCALAPPDATA%/Video DNA Analyzer`
- Linux：`$XDG_DATA_HOME/video-dna-analyzer` 或 `~/.local/share/video-dna-analyzer`

## 代码结构

```text
app/
  embed.go + static/                 内嵌桌面 UI
electron/                            Electron 主进程、预加载与安装包配置
internal/platform/                   平台路径
pkg/xaiapi/                          OpenAI 兼容第三方调用封装
pkg/xffmpeg/                         FFmpeg/FFprobe 进程封装
service/videodna/api/
  videodna.api                       goctl 契约（接口先行）
  etc/                               go-zero 配置
  internal/handler/                  HTTP 解析与响应
  internal/logic/                    用例编排
  internal/service/                  分析、存储、任务、导出、模板、注册表
scripts/                             跨平台后端与 FFmpeg 准备脚本
```

目录和生成流程参考 go-zero 的常规服务约定：先修改 `videodna.api`，再运行：

```bash
cd service/videodna/api
goctl api validate --api videodna.api
goctl api go --api videodna.api --dir . --style go_zero
```

生成后必须保留已有业务实现，建议在独立分支对比生成差异，不要直接覆盖生产 logic。

## 测试

```bash
npm test
go test -race ./...
go vet ./...
```

CI 同时检查 Go 测试、Go vet、后端构建、Electron/前端 JavaScript 语法和 npm 高危漏洞。

## 插件协议

插件 ZIP 必须包含 `manifest.json` 和目标平台可执行文件。后端执行入口时把完整 DNA JSON 写入 stdin，插件把修改后的完整 DNA JSON 写到 stdout。插件拥有当前用户权限，只安装可信来源；安装器会限制文件数、解压大小、路径穿越和符号链接。

## License

[MIT](LICENSE)
