import aiohttp
import logging
import os
from datetime import datetime

INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "iot123token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "my-org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "measurements")

async def write_to_influx(measurement: str, tags: dict, fields: dict, timestamp: datetime):
    # Formato línea de InfluxDB
    tags_str = ",".join(f"{k}={v}" for k, v in tags.items())
    fields_str = ",".join(f"{k}={v}" for k, v in fields.items())

    line = f"{measurement},{tags_str} {fields_str} {int(timestamp.timestamp() * 1e9)}"
    
    url = f"{INFLUX_URL}/api/v2/write?org={INFLUX_ORG}&bucket={INFLUX_BUCKET}&precision=ns"

    headers = {
        "Authorization": f"Token {INFLUX_TOKEN}",
        "Content-Type": "text/plain"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=line) as resp:
            if resp.status != 204:
                text = await resp.text()
                logging.error(f"[Influx] Error al escribir: {resp.status} {text}")
            else:
                logging.info(f"[Influx] Escrito: {line}")
