"""FastAPI 启动入口（薄壳）。

应用配置见 cc_bom_generator.app.create_app。
启动：PYTHONPATH=. uvicorn src.main:app --reload --port 8000
"""

from __future__ import annotations

from src.cc_bom_generator.app import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
