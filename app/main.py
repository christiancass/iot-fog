from fastapi import FastAPI
import logging, os, asyncio

from app.utils.services_ready import wait_influx,wait_grafana
from app.utils.grafana import ensure_datasource
from app.utils.db import connect_to_mongo, close_mongo_connection
from app.utils.influxdb_auth import crear_token_influx  
from app.utils.rules_loader import cargar_alarm_rules_desde_mongo, cargar_save_rules_desde_mongo
from app.apis.emqx_api import router as emqx_api_router, init_emqx_resources

from app.routes.devices import router as device_router
from app.routes.login import router as login_router
from app.routes.users import router as user_router
from app.routes.variables import router as varible_router
from app.routes.webhook import router as webhook_router
from app.routes.alarms import router as alarms_router
from app.routes.dashboard import router as grafana_router


logging.basicConfig(level=logging.INFO)


app = FastAPI()

# Rutas
app.include_router(login_router)
app.include_router(user_router)
app.include_router(device_router)
app.include_router(varible_router)
app.include_router(webhook_router)
app.include_router(emqx_api_router)
app.include_router(alarms_router)
app.include_router(grafana_router)


# Eventos de arranque
@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    await init_emqx_resources()
    await cargar_alarm_rules_desde_mongo()
    await cargar_save_rules_desde_mongo()
    # Esperar InfluxDB
    influx_url = os.getenv("INFLUX_URL", "http://influxdb:8086")
    await wait_influx(influx_url)
    # Crear token Influx y guardar en entorno
    influx_token = await crear_token_influx()
    os.environ["INFLUX_AUTH_TOKEN"] = influx_token
    logging.info("[Startup] Token de InfluxDB guardado en entorno")
    # Espera a Grafana
    await wait_grafana(os.getenv("GRAFANA_URL", "http://grafana:3000"))

     # — NUEVO: grafana multitenant completamente automático —
    await ensure_datasource()

# Eventos de cierre
@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

