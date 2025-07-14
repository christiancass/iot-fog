import os
import logging
import httpx

from app.models.schemas import DashboardConfig

GRAF_URL        = os.getenv("GRAFANA_URL")
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY")
DATASOURCE_UID  = "influx-measurements"

async def ensure_datasource() -> None:
    if not GRAFANA_API_KEY:
        raise RuntimeError("Falta GRAFANA_API_KEY en el .env")

    headers = {
        "Authorization": f"Bearer {GRAFANA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "name": DATASOURCE_UID,
        "type": "influxdb",
        "url": os.getenv("INFLUX_URL"),
        "access": "proxy",
        "database": os.getenv("INFLUX_BUCKET"),
        "jsonData": {
            "organization": os.getenv("INFLUX_ORG"),
            "defaultBucket": os.getenv("INFLUX_BUCKET"),
            "version": "Flux"
        },
        "secureJsonData": {
            "token": os.getenv("INFLUX_AUTH_TOKEN")
        }
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{GRAF_URL}/api/datasources", headers=headers, json=payload)
        if resp.status_code == 200:
            logging.info("[Grafana] Datasource creado")
        elif resp.status_code == 409:
            logging.info("[Grafana] Datasource ya existe")
        else:
            resp.raise_for_status()

async def create_dashboard_dynamic(cfg: DashboardConfig) -> str:
    headers = {
        "Authorization": f"Bearer {GRAFANA_API_KEY}",
        "Content-Type": "application/json"
    }

    panels = []
    for idx, p in enumerate(cfg.panels, start=1):
        panels.append({
            "id": idx,
            "type": p.type,
            "title": p.title,
            "gridPos": p.gridPos or {"h": 8, "w": 24, "x": 0, "y": (idx - 1) * 8},
            "datasource": {"uid": DATASOURCE_UID},
            "targets": [
                {
                    "refId": chr(64 + idx),      # 'A', 'B', ...
                    "queryType": "flux",
                    "datasource": {"uid": DATASOURCE_UID},
                    "flux": p.flux.replace("range(", f'range(start: {cfg.range}) |> ')
                }
            ],
            "fieldConfig": {"defaults": {}, "overrides": []},
            "options": {}
        })

    dashboard_json = {
        "dashboard": {
            "id": None,
            "uid": None,
            "title": cfg.title,
            "timezone": "browser",
            "schemaVersion": 30,
            "version": 0,
            "refresh": "10s",
            "panels": panels
        },
        "overwrite": True
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAF_URL}/api/dashboards/db",
            headers=headers,
            json=dashboard_json
        )
        resp.raise_for_status()
        url = resp.json().get("url")
        logging.info(f"[Grafana] Dashboard dinámico creado: {url}")
        return url
