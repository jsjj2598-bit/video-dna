"""AI 组件注册表：模型 / 组件 / 技能 / 插件 的统一管理。

- 模型（Models）：用户可增删改的 AI 模型配置（OpenAI / 通义 / Ollama / 任意 OpenAI 兼容端点），
  分为 vision（图像理解，供镜头描述使用）与 chat（文本对话，供技能/翻译/摘要使用）。
- 组件（Components）：内置分析能力开关（描述 / ASR / 节拍 / 翻译 / 摘要）。
- 技能（Skills）：提示词模板 + 模型，可对分析结果一键运行（内置 4 个 + 用户自定义）。
- 插件（Plugins）：用户 Python 插件（manifest.json + entry.py + hooks），
  在分析管线中自动执行（on_shots / on_summary），支持 ZIP 安装。

所有用户数据保存在 %APPDATA%/Video DNA Analyzer/config.json（打包版可写路径）。
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import sys
import uuid
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(
    os.environ.get("APPDATA") or str(Path.home())
) / "Video DNA Analyzer"
CONFIG_FILE = DATA_DIR / "config.json"
PLUGIN_DIR = DATA_DIR / "plugins"
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)


# ── 内置模型 ─────────────────────────────────────────────

def _model(
    mid: str, name: str, kind: str, provider: str,
    base_url: str, model: str, api_key: str = "",
) -> dict:
    return {
        "id": mid, "name": name, "kind": kind, "provider": provider,
        "base_url": base_url, "model": model, "api_key": api_key, "builtin": True,
    }


DEFAULT_MODELS = [
    _model("openai-gpt4o", "OpenAI GPT-4o", "vision", "openai",
           "https://api.openai.com/v1", "gpt-4o"),
    _model("openai-gpt4o-mini", "OpenAI GPT-4o Mini", "chat", "openai",
           "https://api.openai.com/v1", "gpt-4o-mini"),
    _model("qwen-vl-max", "通义千问 Qwen-VL-Max", "vision", "dashscope",
           "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-vl-max"),
    _model("qwen-max", "通义千问 Qwen-Max", "chat", "dashscope",
           "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max"),
    _model("ollama-llama3", "Ollama Llama3（本地）", "chat", "ollama",
           "http://localhost:11434/v1", "llama3"),
]


# ── 内置组件 ─────────────────────────────────────────────

DEFAULT_COMPONENTS = {
    "describer": {
        "id": "describer", "name": "镜头语义描述",
        "desc": "对每个镜头生成画面内容、景别、运镜、场景类型与情绪标签",
        "kind": "vision", "icon": "🖼️", "default_on": True,
    },
    "asr": {
        "id": "asr", "name": "语音转写 ASR",
        "desc": "faster-whisper 台词转写 + 语音段落检测 + SRT 字幕",
        "kind": "local", "icon": "🎙️", "default_on": True,
    },
    "beats": {
        "id": "beats", "name": "节拍卡点检测",
        "desc": "BPM 检测、节拍点定位与镜头卡点对齐",
        "kind": "local", "icon": "🥁", "default_on": True,
    },
    "translate": {
        "id": "translate", "name": "台词翻译",
        "desc": "用对话模型将台词翻译为中文（需启用一个 chat 模型）",
        "kind": "chat", "icon": "🌐", "default_on": False,
    },
    "summarize": {
        "id": "summarize", "name": "智能摘要",
        "desc": "用对话模型生成专业剪辑分析摘要（需启用一个 chat 模型）",
        "kind": "chat", "icon": "📝", "default_on": False,
    },
}


# ── 内置技能 ─────────────────────────────────────────────

def _skill(sid: str, name: str, desc: str, prompt: str) -> dict:
    return {"id": sid, "name": name, "desc": desc, "prompt": prompt, "builtin": True}


DEFAULT_SKILLS = [
    _skill(
        "review", "剪辑点评",
        "以专业剪辑师视角点评整支视频的节奏、转场与卡点",
        "你是一位从业 10 年的短视频/中视频剪辑师。请对以下视频分析结果进行专业点评。\n\n"
        "【视频概况】{meta}\n【分析摘要】{summary}\n【镜头列表】{shots}\n【完整台词】{transcript}\n\n"
        "请输出：\n"
        "1. 整体节奏评价（快慢是否合适、平均镜头时长说明什么）\n"
        "2. 卡点与音乐配合评价（BPM {bpm}）\n"
        "3. 转场使用是否得当\n"
        "4. 3 条最具体的改进建议\n"
        "用中文回答，分点列出，语气专业务实。",
    ),
    _skill(
        "structure", "剪辑结构拆解",
        "拆解开头钩子、节奏曲线、结尾设计的结构套路",
        "你是资深视频结构分析师。根据以下数据拆解这支视频的剪辑结构：\n\n"
        "【镜头列表】{shots}\n【摘要】{summary}\n【音频】{audio}\n\n"
        "请输出：\n"
        "1. 开头 10 秒的钩子设计\n"
        "2. 结构曲线：信息密度/情绪强度随时间的变化（用文字描述大致走势）\n"
        "3. 高潮点出现在什么位置、如何铺垫\n"
        "4. 结尾处理方式\n"
        "5. 这套结构属于哪种常见模板（如三段式/钩子-推进-高潮-收尾）\n"
        "用中文回答。",
    ),
    _skill(
        "copywriting", "爆款标题文案",
        "基于内容生成适配抖音/B站/小红书的标题与文案",
        "你是短视频运营专家。根据以下视频内容生成发布文案：\n\n"
        "【摘要】{summary}\n【台词】{transcript}\n【时长】{duration} 秒\n\n"
        "请输出：\n"
        "1. 抖音标题（1 个，20 字内，带悬念或冲突）\n"
        "2. B 站标题（1 个，30 字内，信息明确）\n"
        "3. 小红书标题（1 个，20 字内，带情绪钩子）\n"
        "4. 通用正文文案（100 字内，含 2 个话题标签）\n"
        "用中文回答，直接给出结果。",
    ),
    _skill(
        "emotion_curve", "情绪曲线分析",
        "还原观众情绪随时间的起伏变化",
        "你是观众心理分析师。根据镜头数据还原观看体验的情绪曲线：\n\n"
        "【镜头列表】{shots}\n【音频信息】{audio}\n\n"
        "请输出：\n"
        "1. 情绪曲线描述：用 4~6 个阶段描述观众情绪变化（含大致时间点）\n"
        "2. 情绪峰谷与剪辑手法的对应关系\n"
        "3. 是否存在情绪断层/掉线风险点\n"
        "4. 优化建议\n"
        "用中文回答。",
    ),
]


# ── 配置读写 ─────────────────────────────────────────────

def _load() -> dict:
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        logger.warning("读取配置失败: %s", exc)
    return {}


def _save(cfg: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.error("保存配置失败: %s", exc)


# ── 模型 ─────────────────────────────────────────────────

def list_models() -> list[dict]:
    cfg = _load()
    user_models = cfg.get("models", [])
    merged: dict[str, dict] = {}
    for m in DEFAULT_MODELS:
        merged[m["id"]] = dict(m)
    for m in user_models:
        merged[m["id"]] = dict(m)
    return list(merged.values())


def get_model(mid: str) -> dict | None:
    for m in list_models():
        if m["id"] == mid:
            return m
    return None


def upsert_model(data: dict) -> dict:
    mid = str(data.get("id") or "").strip() or uuid.uuid4().hex[:8]
    name = str(data.get("name") or "").strip()
    kind = data.get("kind") if data.get("kind") in ("vision", "chat") else "chat"
    provider = data.get("provider") if data.get("provider") in ("openai", "dashscope", "ollama", "custom") else "custom"
    base_url = str(data.get("base_url") or "").strip()
    model = str(data.get("model") or "").strip()
    if not name or not base_url or not model:
        raise ValueError("名称、接口地址与模型名不能为空")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("接口地址必须以 http(s):// 开头")
    record = {
        "id": mid, "name": name, "kind": kind, "provider": provider,
        "base_url": base_url.rstrip("/"), "model": model,
        "api_key": str(data.get("api_key") or "").strip(),
        "builtin": False,
    }
    cfg = _load()
    models = {m["id"]: m for m in cfg.get("models", [])}
    models[mid] = record
    cfg["models"] = list(models.values())
    _save(cfg)
    return record


def delete_model(mid: str) -> bool:
    cfg = _load()
    before = len(cfg.get("models", []))
    cfg["models"] = [m for m in cfg.get("models", []) if m["id"] != mid]
    if len(cfg["models"]) != before:
        _save(cfg)
        return True
    return False


def get_enabled_vision_model() -> dict | None:
    """返回启用且有 API Key 的 vision 模型（供镜头描述使用）。"""
    comp = get_component("describer")
    if not comp or not comp.get("enabled", True):
        return None
    mid = comp.get("model_id")
    if mid:
        m = get_model(mid)
        if m and m.get("kind") == "vision" and m.get("api_key"):
            return m
    for m in list_models():
        if m.get("kind") == "vision" and m.get("api_key"):
            return m
    return None


def get_enabled_chat_model() -> dict | None:
    for m in list_models():
        if m.get("kind") == "chat" and m.get("api_key"):
            return m
    return None


# ── 组件 ─────────────────────────────────────────────────

def list_components() -> list[dict]:
    cfg = _load()
    comp_cfg = cfg.get("components", {})
    out = []
    for cid, c in DEFAULT_COMPONENTS.items():
        item = dict(c)
        cc = comp_cfg.get(cid, {})
        item["enabled"] = bool(cc.get("enabled", c.get("default_on", True)))
        item["model_id"] = cc.get("model_id")
        out.append(item)
    return out


def get_component(cid: str) -> dict | None:
    for c in list_components():
        if c["id"] == cid:
            return c
    return None


def set_component(cid: str, enabled: bool, model_id: str | None = None) -> dict | None:
    if cid not in DEFAULT_COMPONENTS:
        return None
    cfg = _load()
    comp_cfg = cfg.setdefault("components", {})
    entry = comp_cfg.setdefault(cid, {})
    entry["enabled"] = bool(enabled)
    if model_id is not None:
        entry["model_id"] = model_id
    _save(cfg)
    return get_component(cid)


# ── 技能 ─────────────────────────────────────────────────

def list_skills() -> list[dict]:
    cfg = _load()
    user_skills = cfg.get("skills", [])
    merged: dict[str, dict] = {}
    for s in DEFAULT_SKILLS:
        merged[s["id"]] = dict(s)
    for s in user_skills:
        merged[s["id"]] = dict(s)
    return list(merged.values())


def add_skill(data: dict) -> dict:
    name = str(data.get("name") or "").strip()
    prompt = str(data.get("prompt") or "").strip()
    if not name or not prompt:
        raise ValueError("名称与提示词不能为空")
    sid = str(data.get("id") or "").strip() or uuid.uuid4().hex[:8]
    record = {
        "id": sid, "name": name,
        "desc": str(data.get("desc") or "").strip(),
        "prompt": prompt, "builtin": False,
    }
    cfg = _load()
    skills = {s["id"]: s for s in cfg.get("skills", [])}
    skills[sid] = record
    cfg["skills"] = list(skills.values())
    _save(cfg)
    return record


def delete_skill(sid: str) -> bool:
    cfg = _load()
    before = len(cfg.get("skills", []))
    cfg["skills"] = [s for s in cfg.get("skills", []) if s["id"] != sid]
    if len(cfg["skills"]) != before:
        _save(cfg)
        return True
    return False


# ── 通用对话调用（OpenAI 兼容协议） ─────────────────────────

def chat_complete(
    model_cfg: dict,
    messages: list[dict],
    json_mode: bool = False,
    timeout: float = 90.0,
) -> str:
    """调用任意 OpenAI 兼容端点（OpenAI / 通义 compatible-mode / Ollama / 自定义）。"""
    import httpx

    url = model_cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    key = model_cfg.get("api_key") or os.environ.get("OPENAI_API_KEY") or ""
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload: dict = {"model": model_cfg["model"], "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"响应格式异常: {data}") from exc


def test_model(model_cfg: dict) -> str:
    """测试模型连通性。"""
    text = chat_complete(
        model_cfg,
        [{"role": "user", "content": "请只回复两个字：正常"}],
        timeout=30.0,
    )
    return (text or "").strip()[:200]


# ── 技能运行 ─────────────────────────────────────────────

def _compact_meta(meta: dict) -> str:
    try:
        return (
            f"时长 {meta.get('duration', '-')}s · 分辨率 {meta.get('width', '-')}x{meta.get('height', '-')} · "
            f"镜头 {meta.get('total_shots', '-')} 个 · 平均 {meta.get('avg_shot_duration', '-')}s · "
            f"卡点率 {round((meta.get('beat_alignment_ratio') or 0) * 100)}%"
        )
    except Exception:
        return str(meta)


def _compact_shots(shots: list[dict], max_shots: int = 60) -> str:
    out = []
    for i, s in enumerate(shots[:max_shots]):
        t = (s.get("transition") or "硬切").replace("cut", "硬切").replace("dissolve", "叠化")
        seg = f"镜头{i} [{s.get('start', 0):.1f}s→{s.get('end', 0):.1f}s] {t}"
        if s.get("content"):
            seg += f" | {s['content']}"
        if s.get("shot_scale") or s.get("camera_motion"):
            seg += f"（{s.get('shot_scale') or ''} {s.get('camera_motion') or ''}）"
        if s.get("emotion"):
            seg += f" 情绪:{s['emotion']}"
        if s.get("transcript"):
            seg += f" 🎤{s['transcript']}"
        out.append(seg)
    if len(shots) > max_shots:
        out.append(f"……（共 {len(shots)} 个镜头，已省略）")
    return "\n".join(out)


def _compact_audio(audio: dict) -> str:
    parts = [f"BPM {audio.get('tempo_bpm', '-')}"]
    if audio.get("beat_count"):
        parts.append(f"节拍 {audio['beat_count']} 个")
    if audio.get("sfx_candidates"):
        parts.append(f"音效候选 {len(audio['sfx_candidates'])} 个")
    if audio.get("speech_regions"):
        parts.append(f"语音段 {len(audio['speech_regions'])} 段")
    if audio.get("language"):
        parts.append(f"语言 {audio['language']}")
    return " · ".join(parts)


def render_skill_prompt(skill: dict, dna: dict) -> str:
    meta = dna.get("meta", {})
    audio = dna.get("audio", {})
    shots = dna.get("shots", [])
    transcript = audio.get("text") or ""
    if not transcript:
        transcript = "，".join(
            s.get("transcript") for s in shots if s.get("transcript")
        )[:4000]
    return skill["prompt"].format(
        meta=_compact_meta(meta),
        summary=dna.get("summary") or "无",
        shots=_compact_shots(shots),
        transcript=(transcript or "无")[:4000],
        audio=_compact_audio(audio),
        bpm=audio.get("tempo_bpm") or "-",
        duration=meta.get("duration") or "-",
    )


def run_skill(skill: dict, dna: dict, model_cfg: dict | None = None) -> str:
    model_cfg = model_cfg or get_enabled_chat_model()
    if not model_cfg:
        raise RuntimeError(
            "没有可用的 chat 模型：请先在「AI 组件」中添加并配置一个对话模型（含 API Key）"
        )
    prompt = render_skill_prompt(skill, dna)
    return chat_complete(
        model_cfg,
        [
            {"role": "system", "content": "你是专业的视频剪辑分析助手，回答简洁、结构清晰。"},
            {"role": "user", "content": prompt},
        ],
    )


# ── 插件 ─────────────────────────────────────────────────

def _plugin_dirs() -> list[Path]:
    dirs = []
    bundled = Path(__file__).resolve().parent.parent / "plugins"
    if bundled.exists():
        dirs.append(bundled)
    if PLUGIN_DIR.exists():
        dirs.append(PLUGIN_DIR)
    return dirs


def _load_plugin_manifest(pdir: Path) -> dict | None:
    mf = pdir / "manifest.json"
    if not mf.exists():
        return None
    try:
        data = json.loads(mf.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        logger.warning("插件 %s 的 manifest 解析失败: %s", pdir.name, exc)
        return None
    if not data.get("id") or not data.get("name"):
        return None
    data.setdefault("version", "1.0")
    data.setdefault("entry", "main.py")
    data.setdefault("hooks", ["on_shots", "on_summary"])
    data.setdefault("enabled", True)
    return data


def list_plugins() -> list[dict]:
    out = []
    for base in _plugin_dirs():
        if not base.exists():
            continue
        for pdir in base.iterdir():
            if not pdir.is_dir():
                continue
            mf = _load_plugin_manifest(pdir)
            if not mf:
                continue
            out.append({
                "id": mf["id"], "name": mf["name"],
                "version": mf.get("version", "1.0"),
                "desc": mf.get("desc", ""),
                "hooks": mf.get("hooks", []),
                "enabled": bool(mf.get("enabled", True)),
                "entry": mf.get("entry", "main.py"),
                "path": str(pdir),
            })
    return out


def _plugin_entry_path(pid: str) -> Path | None:
    for base in _plugin_dirs():
        pdir = base / pid
        if pdir.is_dir():
            mf = _load_plugin_manifest(pdir)
            if mf and mf["id"] == pid:
                return pdir / mf.get("entry", "main.py")
    return None


def _plugin_modules() -> dict[str, dict]:
    modules = {}
    for base in _plugin_dirs():
        if not base.exists():
            continue
        for pdir in base.iterdir():
            if not pdir.is_dir():
                continue
            mf = _load_plugin_manifest(pdir)
            if not mf or not mf.get("enabled", True):
                continue
            entry = pdir / mf.get("entry", "main.py")
            if not entry.exists():
                continue
            try:
                mod_name = f"vdna_plugin_{mf['id']}"
                spec = importlib.util.spec_from_file_location(mod_name, entry)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                hooks = {}
                for h in mf.get("hooks", []):
                    fn = getattr(mod, h, None)
                    if callable(fn):
                        hooks[h] = fn
                modules[mf["id"]] = {"manifest": mf, "module": mod, "hooks": hooks}
            except Exception as exc:
                logger.warning("加载插件 %s 失败: %s", mf["id"], exc)
    return modules


def run_plugin_hooks(dna: dict, ctx: dict | None = None) -> dict:
    """执行所有启用插件的 on_shots / on_summary hooks。"""
    ctx = ctx or {}
    for pid, pl in _plugin_modules().items():
        try:
            if "on_shots" in pl["hooks"]:
                result = pl["hooks"]["on_shots"](dna, ctx)
                if isinstance(result, dict):
                    dna = result
            if "on_summary" in pl["hooks"]:
                result = pl["hooks"]["on_summary"](dna, ctx)
                if isinstance(result, dict):
                    dna = result
        except Exception as exc:
            logger.warning("插件 %s 执行失败: %s", pid, exc)
    return dna


def install_plugin_zip(zip_path: str | Path) -> dict:
    """安装插件 ZIP（内部须包含 manifest.json）。"""
    zip_path = Path(zip_path)
    tmp = DATA_DIR / "install_tmp"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        target = None
        for cand in (tmp, *[d for d in tmp.iterdir() if d.is_dir()]):
            if (cand / "manifest.json").exists():
                target = cand
                break
        if target is None:
            raise ValueError("压缩包内未找到 manifest.json，不是有效的插件包")
        mf = _load_plugin_manifest(target)
        if mf is None:
            raise ValueError("manifest.json 格式不正确")
        dest = PLUGIN_DIR / mf["id"]
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(target, dest)
        return {
            "id": mf["id"], "name": mf["name"], "version": mf.get("version", "1.0"),
            "desc": mf.get("desc", ""), "path": str(dest),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def delete_plugin(pid: str) -> bool:
    removed = False
    for base in _plugin_dirs():
        pdir = base / pid
        if pdir.is_dir() and (pdir / "manifest.json").exists():
            shutil.rmtree(pdir, ignore_errors=True)
            removed = True
    return removed