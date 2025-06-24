from fastapi import FastAPI
import logging
from app.db import connect_to_mongo, close_mongo_connection
from app.routes import router
from app.webhook import router as webhook_router
from app.emqx_api import router as emqx_api_router, init_emqx_resources


logging.basicConfig(level=logging.INFO)

app = FastAPI()

app.include_router(router)
app.include_router(webhook_router)
app.include_router(emqx_api_router)


@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    await init_emqx_resources()
  

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()



