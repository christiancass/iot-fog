import os
import logging
import httpx
from app.models.schemas import DashboardConfig
from dotenv import load_dotenv, set_key

#GRAFANA_URL= os.getenv("GRAFANA_URL")
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY")
DATASOURCE_UID  = os.getenv("DATASOURCE_UID")
ADMIN_USER = os.getenv('GRAFANA_ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.getenv('GRAFANA_ADMIN_PASSWORD', 'admin123..')

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000").rstrip("/")
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY")

#-------------------------------------------------------------
# CREAR SERVICE ACCOUNTS Y TOKEN
#-------------------------------------------------------------
def create_service_account(
    name: str = 'sa-my-automation',
    role: str = 'Admin',
    isDisabled: bool = False
) -> dict:
    """
    Crea un service account solo si no existe ya.
    """
    # 1️⃣ Verificar si ya existe
    url_search = f"{GRAFANA_URL}/api/serviceaccounts/search?query={name}"
    r = httpx.get(url_search, auth=(ADMIN_USER, ADMIN_PASSWORD))
    if r.status_code == 200:
        items = r.json().get("serviceAccounts", [])
        for sa in items:
            if sa.get("name") == name:
                logging.info(f"[Grafana] Service account ya existe: {name} (id={sa.get('id')})")
                return sa  # 👉 reutiliza
    elif r.status_code != 404:
        r.raise_for_status()

    # 2️⃣ Si no existe, crear
    url = f"{GRAFANA_URL}/api/serviceaccounts"
    payload = {"name": name, "role": role, "isDisabled": isDisabled}
    resp = httpx.post(url, auth=(ADMIN_USER, ADMIN_PASSWORD), json=payload)
    if resp.status_code == 201:
        return resp.json()

    # 3️⃣ Manejar errores
    logging.error(f"[Grafana] Error creando SA ({resp.status_code}): {resp.text}")
    resp.raise_for_status()


def list_service_account_tokens(service_account_id: int) -> list[dict]:
    """Lista tokens de un SA (no incluye el secreto)."""
    url = f"{GRAFANA_URL}/api/serviceaccounts/{service_account_id}/tokens"
    resp = httpx.get(url, auth=(ADMIN_USER, ADMIN_PASSWORD))
    if resp.status_code == 200:
        return resp.json() or []
    logging.error(f"[Grafana] Error listando tokens del SA {service_account_id} ({resp.status_code}): {resp.text}")
    resp.raise_for_status()
    return []

def delete_service_account_token(service_account_id: int, token_id: int) -> None:
    """Elimina un token del SA por id."""
    url = f"{GRAFANA_URL}/api/serviceaccounts/{service_account_id}/tokens/{token_id}"
    resp = httpx.delete(url, auth=(ADMIN_USER, ADMIN_PASSWORD))
    if resp.status_code not in (200, 204):
        logging.error(f"[Grafana] Error eliminando token {token_id} del SA {service_account_id} ({resp.status_code}): {resp.text}")
        resp.raise_for_status()

def is_grafana_token_valid(token: str) -> bool:
    """Valida un token probando un endpoint sencillo con Bearer."""
    if not token:
        return False
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{GRAFANA_URL}/api/org"
        r = httpx.get(url, headers=headers, timeout=10.0)
        return r.status_code == 200
    except Exception as ex:
        logging.warning(f"[Grafana] Error validando token: {ex}")
        return False

def create_service_account_token(
    service_account_id: int,
    token_name: str = 'token-for-automation',
    seconds_to_live: int = 0  # 0 = sin expiración
) -> dict:
    """
    Crea un token para el SA y devuelve el JSON con 'key'.
    """
    url = f"{GRAFANA_URL}/api/serviceaccounts/{service_account_id}/tokens"
    payload = {
        "name": token_name,
        "secondsToLive": seconds_to_live
    }
    resp = httpx.post(url, auth=(ADMIN_USER, ADMIN_PASSWORD), json=payload)
    if resp.status_code in (200, 201):
        return resp.json()

    # Si el nombre ya existe, Grafana puede devolver 400 con messageId ErrTokenAlreadyExists
    if resp.status_code in (400, 409):
        logging.error(f"[Grafana] Error creando token ({resp.status_code}): {resp.text}")
    resp.raise_for_status()
    return resp.json()

def setup_grafana_api_key(
    sa_name: str = 'sa-my-automation',
    sa_role: str = 'Admin',
    token_name: str = 'token-for-automation',
    seconds_to_live: int = 0,
    rotate_if_missing_secret: bool = True,
    env_file_path: str = ".env"
) -> str:
    """
    Flujo robusto:
    1) Si GRAFANA_API_KEY existe y es válido -> devuélvelo (no crear nada).
    2) Asegura SA (ya idempotente por tu código).
    3) Intenta crear token (si funciona, guarda 'key' y devuelve).
    4) Si el nombre ya existe y no tenemos 'key':
       - Si GRAFANA_API_KEY válido ya existe -> usa ese y no falles.
       - Si NO tenemos 'key' válido y rotate_if_missing_secret=True -> borrar tokens con ese nombre y crear uno nuevo, guardar y devolver.
       - Si rotate_if_missing_secret=False -> error claro.
    """
    # (1) ¿Ya tengo token en env y sirve?
    existing_env_token = os.getenv("GRAFANA_API_KEY", "")
    if is_grafana_token_valid(existing_env_token):
        logging.info("[Grafana] GRAFANA_API_KEY existente es válido; no se crea uno nuevo.")
        return existing_env_token

    # (2) Asegurar SA (tu función ya lo hace idempotente)
    sa = create_service_account(name=sa_name, role=sa_role, isDisabled=False)
    sa_id = sa.get('id')
    if sa_id is None:
        raise RuntimeError(f"Service Account sin 'id': {sa}")

    # (3) Intentar crear token nuevo (para obtener 'key')
    try:
        token_resp = create_service_account_token(
            service_account_id=sa_id,
            token_name=token_name,
            seconds_to_live=seconds_to_live
        )
        token = token_resp.get('key')
        if not token:
            raise RuntimeError("No se recibió 'key' al crear token")
        # Guardar en .env y en env
        if os.path.exists(env_file_path):
            set_key(env_file_path, "GRAFANA_API_KEY", token)
        os.environ["GRAFANA_API_KEY"] = token
        logging.info("[Grafana] GRAFANA_API_KEY creado y guardado.")
        return token

    except httpx.HTTPStatusError as e:
        # Token duplicado por nombre (tu caso actual)
        status = e.response.status_code if e.response is not None else None
        body = e.response.text if e.response is not None else str(e)
        if status in (400, 409) and "ErrTokenAlreadyExists" in body:
            logging.warning("[Grafana] Ya existe un token con ese nombre para este SA.")
            # ¿Tenemos un token válido en el entorno? (quizá de un run anterior)
            if is_grafana_token_valid(existing_env_token):
                logging.info("[Grafana] Usando GRAFANA_API_KEY existente válido.")
                return existing_env_token

            # No tenemos 'key' válido y el nombre está tomado → ROTAR si está permitido
            if rotate_if_missing_secret:
                logging.warning("[Grafana] Rotando token (borrando tokens con ese nombre y recreando)...")
                tokens = list_service_account_tokens(sa_id)
                to_delete = [t for t in tokens if t.get("name") == token_name]
                for t in to_delete:
                    tid = t.get("id")
                    if tid is not None:
                        delete_service_account_token(sa_id, tid)

                # Crear nuevo (ahora sí debe devolver 'key')
                token_resp2 = create_service_account_token(
                    service_account_id=sa_id,
                    token_name=token_name,
                    seconds_to_live=seconds_to_live
                )
                token2 = token_resp2.get('key')
                if not token2:
                    raise RuntimeError("No se recibió 'key' tras la rotación del token")

                if os.path.exists(env_file_path):
                    set_key(env_file_path, "GRAFANA_API_KEY", token2)
                os.environ["GRAFANA_API_KEY"] = token2
                logging.info("[Grafana] GRAFANA_API_KEY rotado y guardado.")
                return token2

            # No se permite rotar y no hay key válida → error legible
            raise RuntimeError(
                "El token ya existía con ese nombre y no se permite rotación. "
                "Define GRAFANA_API_KEY con un token válido o habilita rotate_if_missing_secret=True."
            ) from e

        # Otro tipo de error → propaga con contexto
        logging.error(f"[Grafana] Error creando token: {status} {body}")
        raise




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

def regenerate_public_dashboard(dashboard_uid: str, time_picker: bool = True, org_id: int = 1) -> dict:
    """
    Regenera el enlace público de un dashboard.
    - Usa primero Bearer (si hay),
    - si 403 -> intenta con Basic Admin + X-Grafana-Org-Id,
    - si sigue sin permiso, hace DELETE (deshabilita) y luego POST (habilita).
    """
    grafana_url = os.getenv("GRAFANA_URL", "http://grafana:3000").rstrip("/")
    api_url = f"{grafana_url}/api/dashboards/uid/{dashboard_uid}/public-dashboards"

    payload = {
        "uid": None,
        "accessToken": None,
        "isEnabled": True,
        "timeSelectionEnabled": bool(time_picker),
        "annotationsEnabled": False,
        "linksEnabled": True
    }

    # Headers comunes
    h_json = {"Content-Type": "application/json"}
    h_org = {"X-Grafana-Org-Id": str(org_id)}

    # 1) Intento con Bearer (si existe), sin org-id primero
    bearer = os.getenv("GRAFANA_API_KEY", "")
    if bearer:
        h_bearer = {**h_json, "Authorization": f"Bearer {bearer}"}
        r = httpx.post(api_url, headers=h_bearer, json=payload, timeout=15.0)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 403:
            # reintento con org-id explícito
            r2 = httpx.post(api_url, headers={**h_bearer, **h_org}, json=payload, timeout=15.0)
            if r2.status_code == 200:
                return r2.json()
            if r2.status_code != 403:
                r2.raise_for_status()
        else:
            r.raise_for_status()

    # 2) Fallback con Basic Admin (permiso garantizado si es Admin de esa org)
    # 2a) Intento directo con POST + org-id
    r3 = httpx.post(api_url, auth=(ADMIN_USER, ADMIN_PASSWORD),
                    headers={**h_json, **h_org}, json=payload, timeout=15.0)
    if r3.status_code == 200:
        return r3.json()

    # 2b) Si sigue dando 403, probamos ciclo duro: DELETE (disable) y POST (enable)
    if r3.status_code == 403:
        # DELETE para deshabilitar (ignora si ya estaba disabled)
        rd = httpx.delete(api_url, auth=(ADMIN_USER, ADMIN_PASSWORD),
                          headers=h_org, timeout=15.0)
        # No detonamos si 404/409 aquí; seguimos al POST de recreación
        r4 = httpx.post(api_url, auth=(ADMIN_USER, ADMIN_PASSWORD),
                        headers={**h_json, **h_org}, json=payload, timeout=15.0)
        r4.raise_for_status()
        return r4.json()

    # Si fue otro error distinto a 403, propága con cuerpo para diagnosticar
    logging.error(f"[Grafana] regenerate_public_dashboard fallo: {r3.status_code} {r3.text}")
    r3.raise_for_status()
    return {}