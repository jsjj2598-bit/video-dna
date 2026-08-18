# 🧬 Video DNA Analyzer

**视频剪辑结构逆向分析引擎**  
上传任意视频 → 自动提取完整剪辑 DNA  

```
分镜边界 → 转场类型(cut/dissolve/fade/white_flash) → BPM节拍卡点 →
音效候选 → ASR台词转写 → 语义描述(景别/相机运动/内容) →
导出 EDL / FCP7 XML / Cutmark JSON → 桌面端(Win/Mac)
```

---

## 🚀 快速开始

### 环境依赖

| 组件 | 最低版本 | 
|------|---------|
| Python | ≥ 3.10 |
| FFmpeg | ≥ 5.0 (含 ffprobe) |
| Node.js | ≥ 18 (桌面端可选) |

### 1️⃣ 安装

```bash
git clone https://github.com/<你的用户名>/video-dna.git
cd video-dna

# Python 依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# (可选) Electron 桌面端
npm install
```

### 2️⃣ CLI 分析

```bash
.venv\Scripts\python -m app.cli 视频.mp4 -o 输出目录

# 完整模式（含描述 + 所有导出格式）
.venv\Scripts\python -m app.cli 视频.mp4 -o 输出目录 --describe --export all
```

### 3️⃣ HTTP Web 服务

```bash
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 浏览器打开 http://localhost:8000
```

### 4️⃣ 🖥️ 桌面端

```bash
npm start
```

自动拉起 Python 后端 + 原生窗口，无需手动操作。

---

## 📦 构建桌面安装包

### Windows

```bash
npm run build:win
# → dist/Video DNA Analyzer Setup.exe (安装版)
# → dist/Video DNA Analyzer Portable.exe (免安装便携版)
```

### macOS

```bash
npm run build:mac
# → dist/Video DNA Analyzer.dmg
```

双击 DMG 拖入 Applications。Apple Silicon + Intel 双架构。

### Linux

```bash
npm run build:linux
# → dist/Video DNA Analyzer.AppImage

chmod +x Video\ DNA\ Analyzer.AppImage
./Video\ DNA\ Analyzer.AppImage
```

---

## 🏗️ 项目架构

```
video-dna/
├── app/                          # Python 分析引擎
│   ├── analyzer/
│   │   ├── ffmpeg_utils.py       # ffprobe / 音频提取 / 帧提取
│   │   ├── shots.py              # PySceneDetect 镜头检测
│   │   ├── transitions.py        # OpenCV BGR 转场分类器
│   │   │                        #   → cut / dissolve / fade / white_flash
│   │   ├── audio.py              # Librosa 音频分析 (向后兼容)
│   │   ├── hpss.py               # 🆕 谐波/打击乐分离 → 更准 BPM
│   │   ├── speech.py             # 🆕 ASR (faster-whisper) / 能量降级
│   │   ├── describer.py          # 🆕 VLM 语义描述 (API/OpenCV 降级)
│   │   └── pipeline.py           # 全管线编排 P0–P5
│   ├── exporter.py               # 🆕 EDL / FCP7 XML / Cutmark JSON 导出
│   ├── main.py                   # FastAPI HTTP 入口 + 关键帧服务 + 导出下载
│   ├── cli.py                    # 命令行入口
│   └── static/index.html         # 暗色主题前端
├── electron/                     # 🆕 Electron 桌面端壳
│   ├── main.js                   # 主进程 (自动启动 Python 后端)
│   ├── preload.js                # IPC 通信桥 (文件对话框/导出/平台)
│   └── builder.yml               # electron-builder 构建配置
├── scripts/                      # 测试视频生成器
├── requirements.txt
├── package.json
└── README.md
```

---

## 📊 输出格式 — 剪辑 DNA JSON

```jsonc
{
  "meta": {
    "duration": 10.0,              // 秒
    "fps": 30.0,
    "resolution": "640x360",
    "total_shots": 4,              // 镜头总数
    "avg_shot_duration": 2.5,      // 平均镜头时长
    "beat_alignment_ratio": 0.75,  // 卡点率
    "transitions": {
      "cut": 2, "dissolve": 1, "fade": 1, "white_flash": 1
    }
  },
  "audio": {
    "tempo_bpm": 117.45,           // BGM BPM
    "beats": [1.022, 1.533, …],    // 节拍时间点
    "beat_count": 16,
    "sfx_candidates": [            // 🆕 音效候选
      {"time": 0.5, "strength": 3.0}
    ],
    "silence_ratio": 0.3,          // 🆕 静音比例
    "speech_regions": [            // 🆕 语音段落
      {"start": 0.116, "end": 2.159, "text": "大家好"}
    ],
    "harmonic": {…},               // 🆕 谐波分量分析
    "percussive": {…}              // 🆕 打击分量分析
  },
  "shots": [
    {
      "index": 0,
      "start": 0.0, "end": 2.0, "duration": 2.0,
      "transition": "cut",         // 🆕 转场类型
      "beat_aligned": true,        // 是否卡点
      "content": "暖色调·中景·固定镜头", // 🆕 语义描述
      "camera_motion": "固定",      // 🆕 相机运动
      "shot_scale": "中景",         // 🆕 景别
      "transcript": "大家好",       // 🆕 台词
      "keyframe": "shot_000.jpg"   // 关键帧
    }
  ],
  "summary": "共 4 个镜头，平均 2.17 秒/镜；转场：硬切×2、叠化×1、闪白×1；BGM 约 117 BPM……"
}
```

### 导出格式

| 格式 | 用途 | CLI | HTTP |
|------|------|-----|------|
| **CMX3600 EDL** | 通用离线编辑交换 | `--export edl` | `/api/export?fmt=edl` |
| **FCP7 XML** | Final Cut Pro 兼容 | `--export fcp7xml` | `/api/export?fmt=fcp7xml` |
| **Cutmark JSON** | 极简切点清单 | `--export cutmark` | `/api/export?fmt=cutmark` |

---

## 🧪 技术栈

| 层 | 实现 |
|----|------|
| 🎬 镜头切分 | PySceneDetect (ContentDetector / AdaptiveDetector) |
| 🔄 转场分类 | OpenCV BGR 三通道帧差 + 亮度分析（支持等亮度异色） |
| 🎵 音频分析 | librosa (BPM/节拍/能量/静音/瞬态) |
| 🎛️ 音频增强 | HPSS 谐波/打击分离 → 纯净 BPM + 干净 SFX |
| 🎙️ ASR 台词 | faster-whisper（需网络）/ 能量检测降级 |
| 🖼️ 语义描述 | OpenAI GPT-4o Vision / 通义千问 VL / OpenCV 启发式降级 |
| 📤 导出 | EDL (CMX3600) / FCP7 XML / Cutmark JSON |
| 🌐 HTTP | FastAPI + uvicorn |
| 🖥️ 桌面端 | Electron + electron-builder |

---

## 🔧 管线流水线

```
上传视频
  │
  ├─ 1. ffprobe → 元数据 (时长 / FPS / 分辨率 / 编码)
  ├─ 2. PySceneDetect → 镜头切分
  ├─ 3. 音频提取 → HPSS 分离
  │     ├─ 谐波分量 → BPM / 节拍
  │     ├─ 打击分量 → SFX 候选
  │     └─ 全信号 → 能量包络 / 静音比例
  ├─ 4. ASR → 台词转写 / 语音段落（失败降级能量检测）
  ├─ 5. OpenCV BGR 转场分类
  ├─ 6. 关键帧提取
  ├─ 7. 语义描述 (VLM API / OpenCV 启发式)
  └─ 8. 导出 (EDL / FCP7 XML / Cutmark)
```

---

## 🤝 贡献 / 后续方向

- **TransNet V2** — 替代 PySceneDetect，准确检测渐变转场
- **Demucs** — 音乐/人声/音效分离 → 独立分析
- **YAMNet / PANN** — 音效精细分类（脚步声、枪声、门铃…）
- **多模态大模型** — GPT-4o / Qwen-VL 精准逐镜头描述
- **剪映草稿 / Final Cut Pro 原生导出**
- **GPU 加速** — CUDA 推理加速

---

## 📄 许可证

MIT