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
async def wait_grafana(url: str, timeout: int = 60):
    """
    Espera hasta que Grafana responda con HTTP 200 en /api/health.
    Levanta TimeoutError si no está listo en `timeout` segundos.
    """
    logging.info(f"Esperando que Grafana esté listo en {url}...")
    deadline = asyncio.get_event_loop().time() + timeout
    async with aiohttp.ClientSession() as session:
        while asyncio.get_event_loop().time() < deadline:
            try:
                async with session.get(f"{url}/api/health", ssl=False) as resp:
                    if resp.status == 200:
                        logging.info("Grafana está listo.")
                        return
            except Exception as e:
                logging.debug(f"Grafana aún no responde: {e}")
            await asyncio.sleep(1)
    raise TimeoutError(f"Timeout esperando a Grafana en {url}")



