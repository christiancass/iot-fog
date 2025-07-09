import aiohttp
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()


GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")

#espear influxdb
async def wait_influx(url: str, timeout: int = 60):
    logging.info(f"Esperando que InfluxDB esté listo en {url}...")
    for _ in range(timeout):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/health", ssl=False) as resp:
                    if resp.status == 200:
                        health = await resp.json()
                        if health.get("status") == "pass":
                            logging.info("InfluxDB está listo.")
                            return
        except Exception as e:
            logging.warning(f"Influx aún no responde: {e}")
        await asyncio.sleep(1)
    raise TimeoutError("Timeout esperando a InfluxDB.")



#esperar grafana
async def wait_grafana(timeout: int = 60):
    logging.info(f"Esperando que Grafana esté listo en {GRAFANA_URL}...")
    for _ in range(timeout):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{GRAFANA_URL}/api/health") as resp:
                    if resp.status == 200:
                        datos = await resp.json()
                        if datos.get("database") == "ok":
                            logging.info("Grafana está listo.")
                            return
        except Exception as e:
            logging.warning(f"Grafana aún no responde: {e}")
        await asyncio.sleep(1)
    raise TimeoutError("Timeout esperando a Grafana.")