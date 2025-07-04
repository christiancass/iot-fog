import os
from fastapi import FastAPI
import logging

from app.utils.db import connect_to_mongo, close_mongo_connection
from app.routes.login import router as login_router
from app.routes.users import router as user_router
from app.routes.devices import router as device_router
from app.routes.variables import router as varible_router
from app.routes.webhook import router as webhook_router
from app.utils.emqx_api import router as emqx_api_router, init_emqx_resources
from app.routes.alarms import router as alarms_router
from app.utils.services_ready import esperar_influx  # aquí está tu función de espera

logging.basicConfig(level=logging.INFO)

app = FastAPI()

# Leer la URL desde el entorno (usa valor por defecto si no existe)
INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")

# Rutas
app.include_router(login_router)
app.include_router(user_router)
app.include_router(device_router)
app.include_router(varible_router)
app.include_router(webhook_router)
app.include_router(emqx_api_router)
app.include_router(alarms_router)

# Eventos de arranque
@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    await init_emqx_resources()
    await esperar_influx(INFLUX_URL) 

# Eventos de cierre
@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()



