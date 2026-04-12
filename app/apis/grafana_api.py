# app/apis/grafana_api.py

import os
import logging
import re
from typing import List, Optional

import httpx
from dotenv import set_key

from app.models.schemas import DashboardConfig

ADMIN_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin123..")

GRAFANA_INTERNAL_URL = os.getenv("GRAFANA_INTERNAL_URL", "http://grafana:3000").rstrip("/")
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY")
DATASOURCE_UID = os.getenv("DATASOURCE_UID")


# ============================================================
# SERVICE ACCOUNT / TOKEN
# ============================================================

def create_service_account(
    name: str = "sa-my-automation",
    role: str = "Admin",
    isDisabled: bool = False,
) -> dict:
    url_search = f"{GRAFANA_INTERNAL_URL}/api/serviceaccounts/search?query={name}"
    r = httpx.get(url_search, auth=(ADMIN_USER, ADMIN_PASSWORD))
    if r.status_code == 200:
        items = r.json().get("serviceAccounts", [])
        for sa in items:
            if sa.get("name") == name:
                logging.info(
                    f"[Grafana] Service account ya existe: {name} (id={sa.get('id')})"
                )
                return sa
    elif r.status_code != 404:
        r.raise_for_status()

    url = f"{GRAFANA_INTERNAL_URL}/api/serviceaccounts"
    payload = {"name": name, "role": role, "isDisabled": isDisabled}
    resp = httpx.post(url, auth=(ADMIN_USER, ADMIN_PASSWORD), json=payload)
    if resp.status_code == 201:
        return resp.json()

    logging.error(
        f"[Grafana] Error creando SA ({resp.status_code}): {resp.text}"
    )
    resp.raise_for_status()
    return {}


def list_service_account_tokens(service_account_id: int) -> List[dict]:
    url = f"{GRAFANA_INTERNAL_URL}/api/serviceaccounts/{service_account_id}/tokens"
    resp = httpx.get(url, auth=(ADMIN_USER, ADMIN_PASSWORD))
    if resp.status_code == 200:
        return resp.json() or []
    logging.error(
        f"[Grafana] Error listando tokens del SA {service_account_id} "
        f"({resp.status_code}): {resp.text}"
    )
    resp.raise_for_status()
    return []


def delete_service_account_token(service_account_id: int, token_id: int) -> None:
    url = f"{GRAFANA_INTERNAL_URL}/api/serviceaccounts/{service_account_id}/tokens/{token_id}"
    resp = httpx.delete(url, auth=(ADMIN_USER, ADMIN_PASSWORD))
    if resp.status_code not in (200, 204):
        logging.error(
            f"[Grafana] Error eliminando token {token_id} del SA {service_account_id} "
            f"({resp.status_code}): {resp.text}"
        )
        resp.raise_for_status()


def is_grafana_token_valid(token: str) -> bool:
    if not token:
        return False
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{GRAFANA_INTERNAL_URL}/api/org"
        r = httpx.get(url, headers=headers, timeout=10.0)
        return r.status_code == 200
    except Exception as ex:
        logging.warning(f"[Grafana] Error validando token: {ex}")
        return False


def create_service_account_token(
    service_account_id: int,
    token_name: str = "token-for-automation",
    seconds_to_live: int = 0,
) -> dict:
    url = f"{GRAFANA_INTERNAL_URL}/api/serviceaccounts/{service_account_id}/tokens"
    payload = {
        "name": token_name,
        "secondsToLive": seconds_to_live,
    }
    resp = httpx.post(url, auth=(ADMIN_USER, ADMIN_PASSWORD), json=payload)
    if resp.status_code in (200, 201):
        return resp.json()

    logging.error(
        f"[Grafana] Error creando token SA {service_account_id} "
        f"({resp.status_code}): {resp.text}"
    )
    resp.raise_for_status()
    return {}


def setup_grafana_api_key(
    sa_name: str = "sa-my-automation",
    sa_role: str = "Admin",
    token_name: str = "token-for-automation",
    seconds_to_live: int = 0,
    rotate_if_missing_secret: bool = True,
    env_file_path: str = ".env",
) -> str:
    existing_env_token = os.getenv("GRAFANA_API_KEY", "")
    if is_grafana_token_valid(existing_env_token):
        logging.info(
            "[Grafana] GRAFANA_API_KEY existente es válido; no se crea uno nuevo."
        )
        return existing_env_token

    sa = create_service_account(name=sa_name, role=sa_role, isDisabled=False)
    sa_id = sa.get("id")
    if sa_id is None:
        raise RuntimeError(f"Service Account sin 'id': {sa}")

    try:
        token_resp = create_service_account_token(
            service_account_id=sa_id,
            token_name=token_name,
            seconds_to_live=seconds_to_live,
        )
        token = token_resp.get("key")
        if not token:
            raise RuntimeError("No se recibió 'key' al crear token")

        if os.path.exists(env_file_path):
            set_key(env_file_path, "GRAFANA_API_KEY", token)
        os.environ["GRAFANA_API_KEY"] = token
        logging.info("[Grafana] GRAFANA_API_KEY creado y guardado.")
        return token

    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else None
        body = e.response.text if e.response is not None else str(e)

        if status in (400, 409) and "ErrTokenAlreadyExists" in body:
            logging.warning(
                "[Grafana] Ya existe un token con ese nombre para este SA."
            )
            if is_grafana_token_valid(existing_env_token):
                logging.info("[Grafana] Usando GRAFANA_API_KEY existente válido.")
                return existing_env_token

            if rotate_if_missing_secret:
                logging.warning(
                    "[Grafana] Rotando token: borrando tokens con ese nombre y recreando..."
                )
                tokens = list_service_account_tokens(sa_id)
                to_delete = [t for t in tokens if t.get("name") == token_name]
                for t in to_delete:
                    tid = t.get("id")
                    if tid is not None:
                        delete_service_account_token(sa_id, tid)

                token_resp2 = create_service_account_token(
                    service_account_id=sa_id,
                    token_name=token_name,
                    seconds_to_live=seconds_to_live,
                )
                token2 = token_resp2.get("key")
                if not token2:
                    raise RuntimeError(
                        "No se recibió 'key' tras la rotación del token"
                    )

                if os.path.exists(env_file_path):
                    set_key(env_file_path, "GRAFANA_API_KEY", token2)
                os.environ["GRAFANA_API_KEY"] = token2
                logging.info("[Grafana] GRAFANA_API_KEY rotado y guardado.")
                return token2

            raise RuntimeError(
                "El token ya existía con ese nombre y no se permite rotación. "
                "Define GRAFANA_API_KEY con un token válido o habilita rotate_if_missing_secret=True."
            ) from e

        logging.error(f"[Grafana] Error creando token: {status} {body}")
        raise


# ============================================================
# DATASOURCE
# ============================================================

async def ensure_datasource() -> None:
    grafana_api_key = os.getenv("GRAFANA_API_KEY")
    if not grafana_api_key:
        raise RuntimeError("Falta GRAFANA_API_KEY en el entorno")

    headers = {
        "Authorization": f"Bearer {grafana_api_key}",
        "Content-Type": "application/json",
    }

    influx_url = os.getenv("INFLUX_URL")
    influx_bucket = os.getenv("INFLUX_BUCKET")
    influx_org = os.getenv("INFLUX_ORG")
    influx_token = os.getenv("INFLUX_AUTH_TOKEN")

    if not influx_url or not influx_bucket or not influx_org or not influx_token:
        raise RuntimeError(
            "Faltan variables de entorno de Influx (INFLUX_URL, INFLUX_BUCKET, "
            "INFLUX_ORG, INFLUX_AUTH_TOKEN)."
        )

    payload = {
        "name": DATASOURCE_UID,
        "type": "influxdb",
        "url": influx_url,
        "access": "proxy",
        "database": influx_bucket,
        "jsonData": {
            "organization": influx_org,
            "defaultBucket": influx_bucket,
            "version": "Flux",
        },
        "secureJsonData": {
            "token": influx_token,
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAFANA_INTERNAL_URL}/api/datasources",
            headers=headers,
            json=payload,
        )
        if resp.status_code == 200:
            logging.info("[Grafana] Datasource creado")
        elif resp.status_code == 409:
            logging.info("[Grafana] Datasource ya existe")
        else:
            resp.raise_for_status()


# ============================================================
# RANGO DEL DASHBOARD (TIME PICKER)
# ============================================================

# Regex simple para validar rangos tipo -1m, -6h, -24h, -7d, etc.
RANGE_RE = re.compile(r"^-?\d+[smhdw]$")


def normalize_dashboard_time(range_str: Optional[str]) -> dict:
    """
    Normaliza y valida el rango del dashboard.
    - Espera valores tipo: -1m, -6h, -24h, -7d, etc.
    - Devuelve dict para el campo "time" de Grafana.
    Si es inválido o viene vacío, cae en 'now-6h'.
    """
    default_from = "now-6h"

    if not range_str:
        return {"from": default_from, "to": "now"}

    r = range_str.strip()

    if not RANGE_RE.match(r):
        logging.warning(f"[Grafana] Rango inválido recibido en cfg.range='{r}', usando now-6h")
        return {"from": default_from, "to": "now"}

    # Si es válido, Grafana espera algo tipo "now-6h"
    return {"from": f"now{r}", "to": "now"}


# ============================================================
# CREAR DASHBOARD DINÁMICO
# ============================================================

async def create_dashboard_dynamic(cfg: DashboardConfig) -> dict:
    """
    Crea un dashboard en Grafana con paneles dinámicos (Influx/Flux).
    El front envía en cada panel:
      - type
      - title
      - flux  (consulta Flux COMPLETA)
      - gridPos

    Además usamos cfg.range para el time picker global del dashboard.
    """
    grafana_api_key = os.getenv("GRAFANA_API_KEY")
    if not grafana_api_key:
        raise RuntimeError("Falta GRAFANA_API_KEY en el entorno")

    datasource_uid = os.getenv("DATASOURCE_UID", "measurements")
    if not datasource_uid:
        raise RuntimeError("Falta DATASOURCE_UID en el entorno")

    headers = {
        "Authorization": f"Bearer {grafana_api_key}",
        "Content-Type": "application/json",
    }

    panels = []
    for idx, p in enumerate(cfg.panels, start=1):
        # Aquí asumimos que p.flux ya es la consulta completa
        flux = p.flux

        panels.append(
            {
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
                        "query": flux,
                    }
                ],
                "fieldConfig": {"defaults": {}, "overrides": []},
                "options": {},
            }
        )

    # Usamos cfg.range para el time picker del dashboard
    dashboard_time = normalize_dashboard_time(getattr(cfg, "range", None))

    dashboard_json = {
        "dashboard": {
            "id": None,
            "uid": None,
            "title": cfg.title,
            "timezone": "browser",
            "schemaVersion": 30,
            "version": 0,
            "refresh": "10s",
            "time": dashboard_time,
            "panels": panels,
        },
        "overwrite": True,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAFANA_INTERNAL_URL}/api/dashboards/db",
            headers=headers,
            json=dashboard_json,
        )
        resp.raise_for_status()
        data = resp.json()
        logging.info(f"[Grafana] Dashboard dinámico creado: {data}")
        return data


# ============================================================
# PUBLIC DASHBOARDS
# ============================================================

def regenerate_public_dashboard(
    dashboard_uid: str,
    time_picker: bool = True,
    org_id: int = 1,
) -> dict:
    grafana_internal = os.getenv("GRAFANA_INTERNAL_URL", "http://grafana:3000").rstrip("/")
    api_url = f"{grafana_internal}/api/dashboards/uid/{dashboard_uid}/public-dashboards"

    bearer = os.getenv("GRAFANA_API_KEY", "")

    headers_json = {"Content-Type": "application/json"}
    payload_create = {
        "isEnabled": True,
        "timeSelectionEnabled": bool(time_picker),
        "annotationsEnabled": False,
        "share": "public",
    }

    def get_with_bearer():
        if not bearer:
            return None
        try:
            r = httpx.get(
                api_url,
                headers={**headers_json, "Authorization": f"Bearer {bearer}"},
                timeout=15.0,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as ex:
            logging.warning(f"[Grafana] GET public-dashboards (Bearer) fallo: {ex}")
            return None

    def get_with_basic():
        try:
            r = httpx.get(
                api_url,
                auth=(ADMIN_USER, ADMIN_PASSWORD),
                headers=headers_json,
                timeout=15.0,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as ex:
            logging.error(f"[Grafana] GET public-dashboards (Basic) fallo: {ex}")
            raise

    def create_with_bearer():
        if not bearer:
            return None
        try:
            r = httpx.post(
                api_url,
                headers={**headers_json, "Authorization": f"Bearer {bearer}"},
                json=payload_create,
                timeout=15.0,
            )
            if r.status_code == 400:
                logging.info("[Grafana] Dashboard ya era público (POST Bearer).")
                return get_with_bearer() or get_with_basic()
            r.raise_for_status()
            return r.json()
        except Exception as ex:
            logging.warning(f"[Grafana] POST public-dashboards (Bearer) fallo: {ex}")
            return None

    def create_with_basic():
        r = httpx.post(
            api_url,
            auth=(ADMIN_USER, ADMIN_PASSWORD),
            headers=headers_json,
            json=payload_create,
            timeout=15.0,
        )
        if r.status_code == 400:
            logging.info("[Grafana] Dashboard ya era público (POST Basic).")
            return get_with_basic()
        r.raise_for_status()
        return r.json()

    data = get_with_bearer()
    if data is None:
        data = get_with_basic()

    if data is None:
        data = create_with_bearer()
        if data is None:
            data = create_with_basic()

    if not isinstance(data, dict):
        raise RuntimeError(f"Respuesta inesperada de public-dashboards: {data!r}")

    if not data.get("isEnabled", False):
        public_uid = data.get("uid")
        if not public_uid:
            raise RuntimeError("Public dashboard sin 'uid' en la respuesta")

        patch_url = f"{api_url}/{public_uid}"
        body = {
            "isEnabled": True,
            "timeSelectionEnabled": bool(time_picker),
            "annotationsEnabled": data.get("annotationsEnabled", False),
            "share": data.get("share", "public"),
        }

        patched = False
        if bearer:
            try:
                r = httpx.patch(
                    patch_url,
                    headers={**headers_json, "Authorization": f"Bearer {bearer}"},
                    json=body,
                    timeout=15.0,
                )
                if r.status_code == 200:
                    data = r.json()
                    patched = True
                else:
                    logging.warning(
                        f"[Grafana] PATCH public-dashboards (Bearer) status={r.status_code} body={r.text}"
                    )
            except Exception as ex:
                logging.warning(f"[Grafana] PATCH public-dashboards (Bearer) fallo: {ex}")

        if not patched:
            r2 = httpx.patch(
                patch_url,
                auth=(ADMIN_USER, ADMIN_PASSWORD),
                headers=headers_json,
                json=body,
                timeout=15.0,
            )
            r2.raise_for_status()
            data = r2.json()

    return data

# ============================================================
# ELIMINAR DASHBOARD DINÁMICO
# ============================================================

async def delete_dashboard_dynamic(dashboard_uid: str) -> None:
    """
    Elimina un dashboard en Grafana usando su UID.
    No toca Mongo, solo Grafana.
    """
    grafana_api_key = os.getenv("GRAFANA_API_KEY")
    if not grafana_api_key:
        raise RuntimeError("Falta GRAFANA_API_KEY en el entorno")

    headers = {
        "Authorization": f"Bearer {grafana_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GRAFANA_INTERNAL_URL}/api/dashboards/uid/{dashboard_uid}",
            headers=headers,
        )

        # 200 / 202 / 204: eliminado OK
        # 404: ya no existe en Grafana, lo ignoramos
        if resp.status_code not in (200, 202, 204, 404):
            logging.error(
                f"[Grafana] Error eliminando dashboard uid={dashboard_uid} "
                f"status={resp.status_code} body={resp.text}"
            )
            resp.raise_for_status()
