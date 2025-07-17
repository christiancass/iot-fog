# app/utils/influx_api.py

import os
import logging
import aiohttp
from datetime import datetime
from dotenv import load_dotenv

# (Opcional) recarga las variables del .env en cada import
load_dotenv(".env", override=True)

async def write_to_influx(measurement: str, tags: dict, fields: dict, timestamp: datetime):
    # Leer en tiempo de ejecución
    INFLUX_URL   = os.getenv("INFLUX_URL", "http://influxdb:8086")
    INFLUX_TOKEN = os.getenv("INFLUX_AUTH_TOKEN")
    INFLUX_ORG   = os.getenv("INFLUX_ORG", "my-org")
    INFLUX_BUCKET= os.getenv("INFLUX_BUCKET", "measurements")

    if not INFLUX_TOKEN:
        raise RuntimeError("Falta INFLUX_AUTH_TOKEN en el entorno")

    # Construye la línea en protocolo de Influx
    tags_str   = ",".join(f"{k}={v}" for k, v in tags.items())
    fields_str = ",".join(f"{k}={v}" for k, v in fields.items())
    line = f"{measurement},{tags_str} {fields_str} {int(timestamp.timestamp() * 1e9)}"

    url = f"{INFLUX_URL}/api/v2/write?org={INFLUX_ORG}&bucket={INFLUX_BUCKET}&precision=ns"
    headers = {
        "Authorization": f"Token {INFLUX_TOKEN}",
        "Content-Type": "text/plain; charset=utf-8"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=line) as resp:
            if resp.status != 204:
                text = await resp.text()
                logging.error(f"[Influx] Error al escribir: {resp.status} {text}")
            else:
                logging.info(f"[Influx] Escrito: {line}")
