import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import admin


def test_restart_endpoint_schedules_backend_restart(monkeypatch):
    scheduled_delays: list[float] = []

    def fake_schedule_backend_restart(delay_seconds: float = 1.0) -> None:
        scheduled_delays.append(delay_seconds)

    monkeypatch.setattr(admin, "schedule_backend_restart", fake_schedule_backend_restart, raising=False)

    app = FastAPI()
    app.include_router(admin.router)
    client = TestClient(app)

    response = client.post("/api/admin/restart")

    assert response.status_code == 202
    assert response.json() == {
        "success": True,
        "message": "后端正在重启，请稍后刷新页面。",
        "restart_scheduled": True,
    }
    assert scheduled_delays == [1.0]
