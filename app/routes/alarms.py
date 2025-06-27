from fastapi import APIRouter, HTTPException, Depends
import logging

from app.routes.auth import get_current_user
from app.db import get_db
from app.routes.schemas import AlarmRuleIn, AlarmRuleOut
from app.emqx_api import crear_regla_alarma

router = APIRouter(prefix="/alarms", tags=["alarms"])

@router.post("", response_model=AlarmRuleOut)
async def create_alarm_rule(
    payload: AlarmRuleIn,
    user: dict = Depends(get_current_user)
):
    db = get_db()
    if db is None:
        raise HTTPException(500, "Base de datos no inicializada")

    # Obtiene la variable por nombre
    filtro = {
        "variable_name": payload.variable_name,
        "device_id": payload.device_id,
        "username": user["username"]
    }
    variable = await db["variables"].find_one(filtro)
    if not variable:
        raise HTTPException(404, f"Variable '{payload.variable_name}' no encontrada")

    variable_id = variable.get("variable_id") or str(variable["_id"])

    # Crea solo la regla instantánea
    try:
        rule_id = await crear_regla_alarma(
            username=user["username"],
            device_id=payload.device_id,
            variable_id=variable_id,
            field=payload.field,
            operator=payload.operator,
            threshold=payload.threshold
        )
    except ValueError as ve:
        logging.error("Parámetros inválidos: %s", ve)
        raise HTTPException(400, str(ve))
    except Exception as e:
        logging.error("Error creando regla de alarma: %r", e)
        raise HTTPException(502, "No se pudo crear la regla de alarma en EMQX")

    return AlarmRuleOut(rule_id=rule_id)
