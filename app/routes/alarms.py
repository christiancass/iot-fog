from fastapi import APIRouter, HTTPException, Depends
import logging

from app.routes.auth import get_current_user
from app.utils.db import get_db
from app.models.schemas import AlarmRuleIn, AlarmRuleOut
from app.apis.emqx_api import crear_regla_alarma

router = APIRouter(prefix="/alarms", tags=["alarms"])

@router.post("", response_model=AlarmRuleOut)
async def create_alarm_rule(
    payload: AlarmRuleIn,
    user: dict = Depends(get_current_user)
):
    db = get_db()
    if db is None:
        raise HTTPException(500, "Base de datos no inicializada")

    # Verificar que la variable existe
    filtro_variable = {
        "variable_name": payload.variable_name,
        "device_id": payload.device_id,
        "username": user["username"]
    }
    variable = await db["variables"].find_one(filtro_variable)
    if not variable:
        raise HTTPException(404, f"Variable '{payload.variable_name}' no encontrada")

    variable_id = variable.get("variable_id") or str(variable["_id"])

    # Verificar si ya existe una regla con los mismos parámetros
    filtro_alarma = {
        "username": user["username"],
        "device_id": payload.device_id,
        "variable_id": variable_id,
        "field": payload.field,
        "operator": payload.operator,
        "threshold": payload.threshold
    }

    regla_existente = await db["alarmas"].find_one(filtro_alarma)
    if regla_existente:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una regla de alarma con las mismas condiciones"
        )

    # Crear la regla en EMQX
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

    # Registrar la regla en la base de datos
    nueva_regla = {
        "rule_id": rule_id,
        "username": user["username"],
        "device_id": payload.device_id,
        "variable_id": variable_id,
        "field": payload.field,
        "operator": payload.operator,
        "threshold": payload.threshold
    }

    await db["alarmas"].insert_one(nueva_regla)

    return AlarmRuleOut(rule_id=rule_id)