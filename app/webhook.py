# routers/webhook.py
from fastapi import APIRouter, Request
import logging

router = APIRouter()

@router.post("/saver-webhook")
async def saver_webhook(req: Request):
    """
    Endpoint que EMQX invocará con cada publicación.
    Imprime el campo `m` del body.
    """
    data = await req.json()
    logging.info(f"WEBHOOK PAYLOAD .m = {data.get('m')!r}")
    return {}
@router.post("/alarms-webhook")
async def saver_webhook(req: Request):
    """
    Endpoint que EMQX invocará con cada publicación.
    Imprime el campo `m` del body.
    """
    data = await req.json()
    logging.info(f"WEBHOOK PAYLOAD .m = {data.get('m')!r}")
    return {}


