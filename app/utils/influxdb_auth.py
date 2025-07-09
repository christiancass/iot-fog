import httpx
import logging
import os

INFLUX_ADMIN_TOKEN = os.getenv("INFLUX_ADMIN_TOKEN")  # Definido sólo una vez en .env para generar otros tokens
INFLUX_ORG = os.getenv("INFLUX_ORG", "my-org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "measurements")

async def crear_token_influx(url: str = os.getenv("INFLUX_URL", "http://influxdb:8086")) -> str:
    headers = {
        "Authorization": f"Token {INFLUX_ADMIN_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        # 1. Obtener ID de organización
        resp_orgs = await client.get(f"{url}/api/v2/orgs?org={INFLUX_ORG}", headers=headers)
        resp_orgs.raise_for_status()
        org_id = resp_orgs.json()["orgs"][0]["id"]
        logging.info(f"[InfluxDB] Organización encontrada: {INFLUX_ORG} (ID: {org_id})")

        # 2. Crear token con permisos limitados
        permissions = [
            {
                "action": "read",
                "resource": {
                    "type": "buckets",
                    "name": INFLUX_BUCKET,
                    "orgID": org_id
                }
            },
            {
                "action": "write",
                "resource": {
                    "type": "buckets",
                    "name": INFLUX_BUCKET,
                    "orgID": org_id
                }
            }
        ]

        payload = {
            "orgID": org_id,
            "description": "Token auto generado para FastAPI",
            "permissions": permissions
        }

        resp_token = await client.post(f"{url}/api/v2/authorizations", headers=headers, json=payload)
        resp_token.raise_for_status()

        token = resp_token.json()["token"]
        logging.info("[InfluxDB] Token generado exitosamente.")
        return token
