"""PyInstaller 后端入口：将 app 作为包导入，保证相对导入正常工作。"""
import os

from app.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("VIDEODNA_HOST", "127.0.0.1"),
        port=int(os.environ.get("VIDEODNA_PORT", "8000")),
        log_level=os.environ.get("VIDEODNA_LOG_LEVEL", "info"),
    )
