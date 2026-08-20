"""AI components, model registry, skills, and plugins."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ... import registry
from ...container import storage
from ...core.security import require_api_token
from ...services.storage import StorageError

router = APIRouter(prefix="/api", tags=["components"], dependencies=[Depends(require_api_token)])

MAX_PLUGIN_BYTES = 50 * 1024 * 1024


def _public_model(model: dict) -> dict:
    item = {key: value for key, value in model.items() if key != "api_key"}
    item["has_api_key"] = bool(model.get("api_key")) or model.get("provider") == "ollama"
    return item


def _public_plugin(plugin: dict) -> dict:
    return {key: value for key, value in plugin.items() if key != "path"}


def _validate_identifier(value: str, label: str) -> str:
    candidate = str(value or "")
    normalized = candidate.replace("-", "").replace("_", "")
    if not normalized or not normalized.isascii() or not normalized.isalnum():
        raise HTTPException(status_code=400, detail=f"{label} 非法")
    return candidate


@router.get("/components")
def get_components():
    return {
        "components": registry.list_components(),
        "models": registry.list_public_models(),
        "plugins": [_public_plugin(plugin) for plugin in registry.list_plugins()],
        "skills": registry.list_skills(),
    }


@router.post("/components/{component_id}/toggle")
def toggle_component(component_id: str, body: dict):
    component = registry.set_component(component_id, bool(body.get("enabled", True)), model_id=body.get("model_id"))
    if component is None:
        raise HTTPException(status_code=404, detail=f"组件不存在: {component_id}")
    return component


@router.post("/models")
def create_model(body: dict):
    try:
        return _public_model(registry.upsert_model(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/models/{model_id}")
def update_model(model_id: str, body: dict):
    body["id"] = _validate_identifier(model_id, "model_id")
    try:
        return _public_model(registry.upsert_model(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/models/{model_id}")
def delete_model(model_id: str):
    _validate_identifier(model_id, "model_id")
    if not registry.delete_model(model_id):
        raise HTTPException(status_code=404, detail=f"模型不存在或不可删除: {model_id}")
    return {"ok": True}


@router.post("/models/{model_id}/test")
def test_model(model_id: str):
    _validate_identifier(model_id, "model_id")
    model = registry.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")
    if not model.get("api_key") and model.get("provider") != "ollama":
        raise HTTPException(status_code=400, detail="请先填写 API Key 再测试")
    try:
        return {"ok": True, "reply": registry.test_model(model)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"连接失败: {exc}") from exc


@router.post("/skills")
def create_skill(body: dict):
    try:
        return registry.add_skill(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/skills/{skill_id}")
def delete_skill(skill_id: str):
    _validate_identifier(skill_id, "skill_id")
    if not registry.delete_skill(skill_id):
        raise HTTPException(status_code=404, detail=f"技能不存在或不可删除: {skill_id}")
    return {"ok": True}


@router.post("/skills/{skill_id}/run")
def run_skill(skill_id: str, body: dict | None = None):
    _validate_identifier(skill_id, "skill_id")
    body = body or {}
    dna = body.get("dna")
    if dna is None and body.get("session_id"):
        try:
            dna = storage.read_result(str(body["session_id"]))
        except StorageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if dna is None:
        raise HTTPException(status_code=400, detail="请提供 dna 或 session_id")
    skill = next((item for item in registry.list_skills() if item["id"] == skill_id), None)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"技能不存在: {skill_id}")
    try:
        return {"ok": True, "output": registry.run_skill(skill, dna), "skill": skill["name"]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/plugins")
def get_plugins():
    return [_public_plugin(plugin) for plugin in registry.list_plugins()]


@router.post("/plugins/install")
async def install_plugin(file: UploadFile = File(...)):
    handle, archive_name = tempfile.mkstemp(suffix=".zip")
    os.close(handle)
    total = 0
    try:
        with open(archive_name, "wb") as archive:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_PLUGIN_BYTES:
                    raise HTTPException(status_code=413, detail="插件包超过 50MB 上限")
                archive.write(chunk)
        plugin = registry.install_plugin_zip(archive_name)
        return {"ok": True, "plugin": _public_plugin(plugin)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        with suppress(FileNotFoundError):
            os.unlink(archive_name)


@router.delete("/plugins/{plugin_id}")
def delete_plugin(plugin_id: str):
    _validate_identifier(plugin_id, "plugin_id")
    if not registry.delete_plugin(plugin_id):
        raise HTTPException(status_code=404, detail=f"插件不存在: {plugin_id}")
    return {"ok": True}
