import os
import logging
import httpx
from app.models.schemas import DashboardConfig
from dotenv import load_dotenv, set_key

GRAFANA_URL= os.getenv("GRAFANA_URL")
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY")
DATASOURCE_UID  = os.getenv("DATASOURCE_UID")
ADMIN_USER = os.getenv('GRAFANA_ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.getenv('GRAFANA_ADMIN_PASSWORD', 'admin123..')


#-------------------------------------------------------------
# CREAR SERVICE ACCOUNTS Y TOKEN
#-------------------------------------------------------------

def create_service_account(
    name: str = 'sa-my-automation',
    role: str = 'Admin',
    is_disabled: bool = False
) -> dict:
    """
    Crea un service account en Grafana con rol Admin y devuelve el JSON de la cuenta.
    """
    url = f"{GRAFANA_URL}/api/serviceaccounts"
    payload = {
        "name": name,
        "role": role,
        "isDisabled": is_disabled
    }
    resp = httpx.post(url, auth=(ADMIN_USER, ADMIN_PASSWORD), json=payload)
    resp.raise_for_status()
    return resp.json()

def create_service_account_token(
    service_account_id: int,
    token_name: str = 'token-for-automation',
    expiration_seconds: int = 0
) -> dict:
    """
    Genera un token para el service account indicado y devuelve el JSON con el campo 'key'.
    """
    url = f"{GRAFANA_URL}/api/serviceaccounts/{service_account_id}/tokens"
    payload = {
        "name": token_name,
        "expirationSeconds": expiration_seconds
    }
    resp = httpx.post(url, auth=(ADMIN_USER, ADMIN_PASSWORD), json=payload)
    resp.raise_for_status()
    return resp.json()

def setup_grafana_api_key(
    sa_name: str = 'sa-my-automation',
    # ahora por defecto creamos como Admin
    sa_role: str = 'Admin',
    token_name: str = 'token-for-automation',
    expiration_seconds: int = 0
) -> str:
    """
    Crea (o vuelve a crear) un service account con rol Admin y su token,
    y devuelve el token para almacenar en GRAFANA_API_KEY.
    """
    # 1) Creamos la cuenta en modo Admin
    sa = create_service_account(name=sa_name, role=sa_role, is_disabled=False)
    sa_id = sa.get('id')

    # 2) Generamos el token
    token_resp = create_service_account_token(
        service_account_id=sa_id,
        token_name=token_name,
        expiration_seconds=expiration_seconds
    )
    token = token_resp.get('key')
    if not token:
        raise RuntimeError("No se recibió el campo 'key' en la respuesta de token")

    return token

#-------------------------------------------------------------
# CREAR DATASOURCE
#-------------------------------------------------------------
async def ensure_datasource() -> None:
    # Leer la clave en el momento de la llamada
    grafana_api_key = os.getenv("GRAFANA_API_KEY")
    if not grafana_api_key:
        raise RuntimeError("Falta GRAFANA_API_KEY en el entorno")

    headers = {
        "Authorization": f"Bearer {grafana_api_key}",
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
        resp = await client.post(f"{GRAFANA_URL}/api/datasources", headers=headers, json=payload)
        if resp.status_code == 200:
            logging.info("[Grafana] Datasource creado")
        elif resp.status_code == 409:
            logging.info("[Grafana] Datasource ya existe")
        else:
            resp.raise_for_status()
#-------------------------------------------------------------
# CREAR DASHBOARD DINAMICO
#-------------------------------------------------------------
import os, logging, httpx
from app.models.schemas import DashboardConfig

async def create_dashboard_dynamic(cfg: DashboardConfig) -> str:
    """
    Crea un dashboard en Grafana donde cada panel parte de los mismos filtros:
      - measurement == iot_data
      - _field == cfg.field (por defecto "value")
      - filtros por device_id, username, variable_id
    y luego aplica la función particular de cada panel (mean(), last(), etc.).
    Devuelve la URL del dashboard.
    """
    # --- 1) Validaciones y setup ---
    grafana_api_key = os.getenv("GRAFANA_API_KEY")
    if not grafana_api_key:
        raise RuntimeError("Falta GRAFANA_API_KEY en el entorno")

    datasource_uid = os.getenv("DATASOURCE_UID", "measurements")
    if not datasource_uid:
        raise RuntimeError("Falta DATASOURCE_UID en el entorno")

    base_url = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
    headers = {
        "Authorization": f"Bearer {grafana_api_key}",
        "Content-Type": "application/json"
    }

    # --- 2) Construir los filtros comunes ---
    # measurement y campo
    measurement = cfg.measurement  # p.ej. "iot_data"
    field       = getattr(cfg, "field", "value")

    # filtros de tags: device_id, username, variable_id
    # asumo que cfg.tagFilters es un dict con esas claves
    tag_filters = []
    for tag in ("device_id", "username", "variable_id"):
        val = cfg.tagFilters.get(tag)
        if not val:
            raise RuntimeError(f"Falta filtro '{tag}' en cfg.tagFilters")
        tag_filters.append(f'r["{tag}"] == "{val}"')
    tag_filter_flux = " |> filter(fn: (r) => " + " and ".join(tag_filters) + ")"

    # --- 3) Paneles ---
    panels = []
    for idx, p in enumerate(cfg.panels, start=1):
        # Base Flux para este panel
        flux = (
            f'from(bucket: "{cfg.bucket}")'
            f' |> range(start: {cfg.range})'
            f' |> filter(fn: (r) => r._measurement == "{measurement}")'
            f' |> filter(fn: (r) => r._field == "{field}")'
            f'{tag_filter_flux}'
            # ahora la transformación específica
            f' |> {p.flux}'
        )

        # creacion de paneles
        panels.append({
            "id": idx,
            "type": p.type,
            "title": p.title,
            "gridPos": p.gridPos or {"h": 8, "w": 24, "x": 0, "y": (idx - 1) * 8},
            "datasource": {"uid": datasource_uid},
            "targets": [
                {
                    "refId": chr(64 + idx),
                    "queryType": "flux",
                    "datasource": {"uid": datasource_uid},
                    # <— cambia "flux" por "query"
                    "query": p.flux  
                }
            ],
            "fieldConfig": {"defaults": {}, "overrides": []},
            "options": {}
        })

    # --- 4) Crear el dashboard en Grafana ---
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
        resp = await client.post(f"{base_url}/api/dashboards/db", headers=headers, json=dashboard_json)
        resp.raise_for_status()
        url = resp.json().get("url")
        logging.info(f"[Grafana] Dashboard dinámico creado: {url}")
        return url
