import os
import logging
import httpx
from dotenv import load_dotenv, set_key

load_dotenv(".env")

INFLUX_ADMIN_TOKEN = os.getenv("INFLUX_ADMIN_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG", "my-org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "measurements")

async def crear_token_influx(url: str = os.getenv("INFLUX_URL", "http://influxdb:8086")) -> str:
    if not INFLUX_ADMIN_TOKEN:
        raise RuntimeError("Falta INFLUX_ADMIN_TOKEN en el entorno")

    headers = {
        "Authorization": f"Token {INFLUX_ADMIN_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        # 1. Obtener orgID
        resp_orgs = await client.get(f"{url}/api/v2/orgs?org={INFLUX_ORG}", headers=headers)
        resp_orgs.raise_for_status()
        orgs = resp_orgs.json().get("orgs", [])
        if not orgs:
            raise RuntimeError(f"Organización '{INFLUX_ORG}' no encontrada")
        org_id = orgs[0]["id"]
        logging.info(f"[InfluxDB] Organización ID: {org_id}")

        # 2. Obtener bucketID
        resp_buckets = await client.get(f"{url}/api/v2/buckets?name={INFLUX_BUCKET}", headers=headers)
        resp_buckets.raise_for_status()
        buckets = resp_buckets.json().get("buckets", [])
        if not buckets:
            raise RuntimeError(f"Bucket '{INFLUX_BUCKET}' no encontrado")
        bucket_id = buckets[0]["id"]
        logging.info(f"[InfluxDB] Bucket ID: {bucket_id}")

        # 3. Crear token con permisos read/write
        payload = {
            "description": f"auto-token-{INFLUX_BUCKET}",
            "orgID": org_id,
            "permissions": [
                {"action": "read", "resource": {"type": "buckets", "orgID": org_id, "id": bucket_id}},
                {"action": "write", "resource": {"type": "buckets", "orgID": org_id, "id": bucket_id}}
            ]
        }
        resp_token = await client.post(f"{url}/api/v2/authorizations", headers=headers, json=payload)
        resp_token.raise_for_status()
        token = resp_token.json().get("token")
        if not token:
            raise RuntimeError("No se recibió token al crear autorización")
        logging.info("[InfluxDB] Token generado correctamente")

        # 4. Persistir en .env
        set_key(".env", "INFLUX_AUTH_TOKEN", token)
        os.environ["INFLUX_AUTH_TOKEN"] = token
        logging.info("[InfluxDB] INFLUX_AUTH_TOKEN guardado en .env y env vars")

        return token
