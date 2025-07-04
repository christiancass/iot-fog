import aiohttp
import asyncio
import logging

async def esperar_influx(url: str, timeout: int = 60):
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
