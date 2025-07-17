
import os
import logging
import asyncio
from dotenv import load_dotenv, set_key

from fastapi import FastAPI
from app.utils.services_ready import wait_influx, wait_grafana
from app.utils.influxdb_auth import crear_token_influx
from app.utils.db import connect_to_mongo, close_mongo_connection
from app.apis.influx_api import write_to_influx
from app.utils.rules_loader import cargar_alarm_rules_desde_mongo, cargar_save_rules_desde_mongo
from app.apis.emqx_api import router as emqx_api_router, init_emqx_resources
from app.apis.grafana_api import setup_grafana_api_key, ensure_datasource
from app.routes.devices import router as device_router
from app.routes.login import router as login_router
from app.routes.users import router as user_router
from app.routes.variables import router as variable_router
from app.routes.webhook import router as webhook_router
from app.routes.alarms import router as alarms_router
from app.routes.dashboard import router as grafana_router

logging.basicConfig(level=logging.INFO)
load_dotenv(".env")

app = FastAPI()

# Routers
app.include_router(login_router)
app.include_router(user_router)
app.include_router(device_router)
app.include_router(variable_router)
app.include_router(webhook_router)
app.include_router(emqx_api_router)
app.include_router(alarms_router)
app.include_router(grafana_router)

@app.on_event("startup")
async def startup_event():
    # MongoDB
    await connect_to_mongo()

    # EMQX
    await init_emqx_resources()

    # Load rules
    await cargar_alarm_rules_desde_mongo()
    await cargar_save_rules_desde_mongo()

    # InfluxDB ready
    influx_url = os.getenv("INFLUX_URL", "http://influxdb:8086")
    await wait_influx(influx_url)

    # Create Influx token
    influx_token = await crear_token_influx()
    os.environ["INFLUX_AUTH_TOKEN"] = influx_token
    set_key(".env", "INFLUX_AUTH_TOKEN", influx_token)
    logging.info(f"[Startup] INFLUX_AUTH_TOKEN set to: {influx_token}")

    # Grafana ready
    grafana_url = os.getenv("GRAFANA_URL", "http://grafana:3000")
    await wait_grafana(grafana_url)

    # Create Grafana SA & token
    grafana_token = setup_grafana_api_key()
    os.environ["GRAFANA_API_KEY"] = grafana_token
    set_key(".env", "GRAFANA_API_KEY", grafana_token)
    logging.info(f"[Startup] GRAFANA_API_KEY set to: {grafana_token}")

    # Ensure Grafana datasource exists
    await ensure_datasource()

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()
