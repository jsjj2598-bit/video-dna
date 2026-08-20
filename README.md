# Video DNA Analyzer

本地优先的视频剪辑结构分析工具。它把一支成片拆解为镜头、转场、节拍、台词、关键帧和语义标签，并输出可继续处理的剪辑 DNA 数据。

> 项目当前处于 alpha 阶段。基础分析和 Cutmark/SRT 可用于实际工作流；EDL、FCP7 XML 和剪映草稿在正式生产使用前，应使用目标剪辑软件完成兼容性验证。

## 功能

- PySceneDetect 镜头切分和 OpenCV 转场分类。
- librosa HPSS、BPM、节拍、静音和强瞬态分析。
- 可选 faster-whisper 台词转写，失败时降级为能量区域检测。
- OpenCV 启发式镜头标签，或接入 OpenAI、通义千问、Ollama/OpenAI 兼容视觉模型。
- 可交互时间轴、关键帧、历史回看和视频 Range 播放。
- EDL、FCP7 XML、Cutmark JSON、SRT 和剪映草稿导出。
- 内置节奏模板、分镜脚本和 BGM 风格建议。
- CLI、FastAPI Web 服务和 Electron 桌面端。

## 运行要求

- Python 3.10–3.12，推荐 Python 3.11。
- FFmpeg/ffprobe 5.0 或更高版本。
- Node.js 18 或更高版本，仅桌面端需要。

## 安装

基础分析环境：

```bash
git clone https://github.com/jsjj2598-bit/video-dna.git
cd video-dna
python3.11 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e .
```

包含 Whisper ASR：

```bash
pip install -e ".[asr]"
```

开发环境：

```bash
pip install -e ".[asr,dev]"
npm ci
```

## 使用

### CLI

```bash
video-dna input.mp4 -o output --export all

# 不提取关键帧或不做语义描述
video-dna input.mp4 -o output --no-keyframes --no-describe

# 批量分析目录
video-dna --input-dir ./videos -o output --export srt
```

### Web 服务

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000>。默认只建议本机使用。

如确实需要通过其他设备访问，应配置随机 Token 并在受信任的 TLS 反向代理后运行：

```bash
export VIDEODNA_API_TOKEN="replace-with-a-long-random-secret"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

所有 `/api/*` 请求需携带：

```text
X-VideoDNA-Token: replace-with-a-long-random-secret
```

使用内置 Web UI 时，可首次访问 `http://主机:8000/?token=...`。服务校验后会写入仅同源使用的 HttpOnly Cookie，页面随后会从地址栏移除 Token。

### Electron 桌面端

```bash
npm start
```

桌面端会启动本地后端。原生文件选择使用流式 multipart 上传，不会再把整个视频转换成 Base64 放进 IPC。

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `VIDEODNA_DATA_DIR` | 平台用户数据目录 | 配置、插件、上传历史和下载目录 |
| `VIDEODNA_MAX_UPLOAD_BYTES` | 2GB | 单个上传文件上限 |
| `VIDEODNA_MAX_HISTORY_BYTES` | 8GB | 历史数据总量上限 |
| `VIDEODNA_TASK_TTL_SECONDS` | 24 小时 | 完成任务进度在内存中的保留时间 |
| `VIDEODNA_API_TOKEN` | 空 | 配置后启用 API Token 校验 |

平台默认数据目录：

- macOS：`~/Library/Application Support/Video DNA Analyzer`
- Windows：`%LOCALAPPDATA%\Video DNA Analyzer`
- Linux：`$XDG_DATA_HOME/video-dna-analyzer` 或 `~/.local/share/video-dna-analyzer`

## 项目架构

```text
app/
├── api/
│   ├── router.py                 # 路由组合
│   └── routes/
│       ├── analysis.py           # 分析提交、进度和结果
│       ├── media.py              # 历史、关键帧、视频流
│       ├── exports.py            # EDL/XML/JSON/SRT 导出
│       ├── studio.py             # 模板、草稿、分镜、BGM
│       └── components.py         # 模型、组件、技能、插件
├── core/
│   ├── config.py                 # 版本、环境变量和平台目录
│   └── security.py               # 可选 Token 认证
├── services/
│   ├── analysis.py               # 分析用例编排
│   ├── storage.py                # 上传、结果和历史持久化
│   ├── tasks.py                  # 有界线程安全进度状态
│   └── templates.py              # 节奏模板和切点映射
├── analyzer/                     # 镜头、音频、ASR、VLM 算法
├── static/
│   ├── index.html
│   ├── app.css
│   └── js/                        # core/history/analysis/components/studio
├── main.py                       # FastAPI 应用工厂
├── exporter.py
├── draft.py
├── registry.py
└── cli.py
electron/                         # 桌面端进程和打包配置
tests/                            # 回归测试
```

设计约束：

- 路由只处理 HTTP 输入输出，不直接维护任务全局状态。
- 后续操作必须使用 `session_id`，不依赖“最近一次分析”。
- API Key 按请求或模型客户端传递，不写入进程级临时环境变量。
- 完整结果保存到 session 的 `result.json`，内存只保存有限进度日志。
- 用户数据不写入源代码目录或桌面应用安装目录。

## 分析输出

```json
{
  "meta": {
    "duration": 10.0,
    "fps": 30.0,
    "resolution": "640x360",
    "total_shots": 4,
    "avg_shot_duration": 2.5,
    "beat_alignment_ratio": 0.75,
    "transitions": { "cut": 3 }
  },
  "audio": {
    "tempo_bpm": 117.45,
    "beats": [1.022, 1.533],
    "speech_regions": []
  },
  "shots": [
    {
      "index": 0,
      "start": 0.0,
      "end": 2.0,
      "transition": "cut",
      "beat_aligned": true,
      "content": "远景·暖色调·固定",
      "keyframe": "shot_000.jpg"
    }
  ],
  "summary": "共 4 个镜头……"
}
```

## 测试与质量检查

```bash
ruff check app tests
pytest
python -m compileall -q app
node --check electron/main.js
node --check electron/preload.js
for file in app/static/js/*.js; do node --check "$file"; done
```

涉及导出格式的提交，除自动化测试外，还应在目标剪辑软件中完成导入验证。

## 安全

- 不要把未设置 Token 的服务暴露到局域网或公网。
- 插件是具有当前用户完整权限的 Python 代码，只安装可信插件。
- HTTP 模型列表不会返回明文 API Key；配置文件仍应被视为敏感数据。
- 安全问题请参考 [SECURITY.md](SECURITY.md)。

## 参与贡献

开发流程和代码组织约束见 [CONTRIBUTING.md](CONTRIBUTING.md)，问题与优化路线见 [BUGS_AND_OPTIMIZATIONS.md](BUGS_AND_OPTIMIZATIONS.md)。

## License

[MIT](LICENSE)
