# Video DNA Analyzer Bug 清单与优化清单

> 更新日期：2026-08-20
> 基线：`f2c6735` 后的 Go v0.4.0 重构工作区
> 审计方式：Go/JavaScript 静态检查、单元测试、真实 FFmpeg 合成视频端到端烟测、导出与剪映草稿结构检查。

## 总体结论

项目已经从 Python/FastAPI/PyInstaller 后端迁移到 Go + go-zero。UI 仍由 Electron 展示，但静态资源内嵌在 Go 可执行文件里；本机 HTTP 只承担 Electron 与分析引擎之间的进程通信。基础分析、历史、关键帧、导出、模板、组件、技能和插件接口均已迁移，Windows 后端可直接交叉编译。

本轮烟测结果：

- `go test ./...`、`npm test` 通过。
- 2 秒 H.264/AAC 样例完成同步分析，生成关键帧、BPM、镜头描述和历史记录。
- EDL、FCP7 XML、Cutmark JSON、SRT 与全量 ZIP 导出成功。
- 剪映草稿生成成功，包含时间线 JSON、元信息、封面和源视频副本。
- 独立 Go 后端启用 `CGO_ENABLED=0` 构建；Windows `backend.exe` 可在 macOS 直接交叉编译。
- Windows x64 的 NSIS 安装版与 portable 版已在 macOS 交叉打包成功，并核对包内 Go 后端、FFmpeg、FFprobe 架构。

## Bug 清单

| 优先级 | 问题 | 当前状态 | 建议 |
| --- | --- | --- | --- |
| P1 | ASR 组件目前是预留接口，启用后尚未调用 whisper.cpp | 未完成，默认关闭 | 增加 `pkg/xwhisper`，明确二进制/模型路径、超时和字幕映射 |
| P1 | 转场识别当前只可靠标记硬切，未做叠化/闪白视觉分类 | 部分完成 | 用 FFmpeg 多窗口差分或独立纯 Go 特征器补分类与黄金视频测试 |
| P1 | macOS 安装包复制宿主 FFmpeg，动态库在干净机器上的可移植性未完整验证 | 待验收 | 使用可再分发的固定构建或归档所有依赖，并在干净 Intel/Apple Silicon 机器安装测试 |
| P1 | EDL/FCP7 XML/剪映草稿尚未在多款真实剪辑软件完成导入验收 | 待验收 | 至少覆盖剪映、Resolve 或 Premiere/FCP 中两种，建立样例和截图记录 |
| P2 | 插件有 ZIP 安全校验，但没有签名、发布者和权限确认 | 未完成 | 增加签名/哈希信任库，安装时展示入口与 hooks |
| P2 | Electron 固定默认端口 8000；已有其他 Video DNA 实例时会复用 | 未完成 | 主进程选择空闲端口并通过环境变量传递 |
| P2 | 模型密钥仍是权限受限的本地 JSON，不是系统凭据库 | 未完成 | Electron IPC 接入 Keychain/Credential Manager |
| P2 | 纯 Go BPM 为轻量自相关算法，复杂音乐、变速音乐准确率有限 | 可用但可优化 | 增加节奏评测集、半拍/双拍归一化与置信度 |
| P2 | 草稿导出会复制整段源视频，长视频占用空间和时间较大 | 设计限制 | 提供引用原素材/复制素材两种模式和进度提示 |
| P3 | 大文件 multipart 由标准库落临时文件，异常退出可能留下系统临时文件 | 低风险 | 请求结束显式 `RemoveAll` multipart 临时数据，启动时清理过期临时目录 |
| P3 | 安装包尚未配置产品图标，当前显示 Electron 默认图标 | 不影响功能 | 补齐 `.ico`/`.icns`/PNG 图标并启用可执行文件元信息写入 |

## 已关闭的主要问题

- 历史容量清理误删：现在删除前计算大小，只删到目标容量。
- API Key 串任务：分析密钥只在请求选项与客户端对象中传递，不修改进程环境。
- 最近任务全局状态：所有后续操作显式使用 `session_id`。
- EDL 固定硬切：按转场类型输出 `C` 或 `D + 持续帧数`。
- FCP7 XML 离线素材：统一引用源视频 URI 与正确入出点。
- SRT 产生 `1000ms`：先转整数毫秒再拆分时间戳。
- 短视频模板负时长/越界：边界带最小时长与目标时长约束。
- Electron Base64 上传：主进程流式 multipart，不经 IPC 复制大文件。
- API 无认证/密钥泄漏：可选 token 保护 `/api`，模型列表不返回明文密钥。
- Python 运行时过重：删除 Python 服务、虚拟环境和 PyInstaller 构建链，Go 后端无 CGO。
- 插件 zip-slip/解压炸弹：限制路径、符号链接、文件数、总解压大小和输出大小。

## 优化清单

### 下一版本优先

- [ ] 完成 whisper.cpp ASR 可执行组件和模型管理。
- [ ] 完成叠化、淡入淡出、闪白转场分类。
- [ ] 做 1 小时/4K/高码率视频的内存、磁盘和取消压力测试。
- [ ] 在干净 Windows 11 上验证 NSIS、portable、FFmpeg、草稿导出完整链路。
- [ ] 在干净 macOS arm64/x64 上验证 FFmpeg 可移植性。
- [ ] 用真实剪辑软件验证 EDL、XML、SRT 与剪映草稿。

### 工程质量

- [ ] 增加 API 级 `httptest` 回归和 multipart 大小边界测试。
- [ ] 给 FFprobe/FFmpeg 命令增加可替换接口，便于错误注入测试。
- [ ] 增加 `golangci-lint`、前端 ESLint 和依赖许可证检查。
- [x] 为 Windows release 固定 FFmpeg 版本与 checksum，不跟随 latest release。
- [ ] 生成 SBOM，并为安装包提供签名与校验文件。
- [ ] 增加正式产品图标、Windows 元信息和 macOS 公证配置。
- [ ] 增加任务取消接口和进程树强制回收。
