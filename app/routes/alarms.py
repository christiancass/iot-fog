from fastapi import APIRouter, HTTPException, Depends, Query
import logging
from typing import Optional, List, Dict, Any

from app.routes.auth import get_current_user
from app.utils.db import get_db
from app.models.schemas import AlarmRuleIn, AlarmRuleOut
from app.apis.emqx_api import crear_regla_alarma, emqx_delete


# Intentar importar la función de borrado en EMQX (si existe)
try:
    from app.apis.emqx_api import eliminar_regla_alarma  # async
except Exception:  # pragma: no cover
    eliminar_regla_alarma = None  # manejar como opcional

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
        "threshold": payload.threshold,
        "window_s": payload.window_s,  # guardamos si viene
    }

    await db["alarmas"].insert_one(nueva_regla)
    return AlarmRuleOut(rule_id=rule_id)


# ---------- GET: listar reglas del usuario (filtros opcionales) ----------
@router.get("", response_model=List[Dict[str, Any]])
async def list_alarm_rules(
    device_id: Optional[str] = Query(default=None, description="Filtrar por device_id"),
    variable_id: Optional[str] = Query(default=None, description="Filtrar por variable_id"),
    user: dict = Depends(get_current_user)
):
    """
    Lista las reglas de alarma del usuario autenticado.
    Permite filtrar opcionalmente por device_id y/o variable_id.
    """
    db = get_db()
    if db is None:
        raise HTTPException(500, "Base de datos no inicializada")

    filtro = {"username": user["username"]}
    if device_id:
        filtro["device_id"] = device_id
    if variable_id:
        filtro["variable_id"] = variable_id

    cursor = db["alarmas"].find(filtro)
    reglas: List[Dict[str, Any]] = []
    async for r in cursor:
        reglas.append({
            "id": str(r.get("_id")),
            "rule_id": r.get("rule_id"),
            "username": r.get("username"),
            "device_id": r.get("device_id"),
            "variable_id": r.get("variable_id"),
            "field": r.get("field"),
            "operator": r.get("operator"),
            "threshold": r.get("threshold"),
            "window_s": r.get("window_s"),
        })

    return reglas


# ---------- DELETE: eliminar por rule_id ----------
@router.delete("/{rule_id}")
async def delete_alarm_rule(
    rule_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Elimina una regla de alarma por su rule_id.
    - Borra primero la regla en EMQX.
    - Luego elimina el registro local en 'alarmas'.
    """
    db = get_db()
    if db is None:
        raise HTTPException(500, "Base de datos no inicializada")

    # 1) Verificar que exista y pertenezca al usuario
    regla = await db["alarmas"].find_one({"rule_id": rule_id, "username": user["username"]})
    if not regla:
        raise HTTPException(404, "Regla no encontrada o no pertenece al usuario")

    # 2) Borrar en EMQX
    try:
        await emqx_delete(f"/rules/{rule_id}")
        logging.info("[alarms][delete] Regla EMQX %s eliminada", rule_id)
    except Exception as e:
        # No bloqueamos el borrado local, pero dejamos trazabilidad
        logging.warning("[alarms][delete] Error eliminando regla en EMQX (rule_id=%s): %r", rule_id, e)

    # 3) Borrar en BD
    result = await db["alarmas"].delete_one({"rule_id": rule_id, "username": user["username"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "No se pudo eliminar la regla localmente")

    logging.info("[alarms][delete] Regla %s eliminada en Mongo para usuario %s", rule_id, user["username"])
    return {"message": "Regla eliminada correctamente", "rule_id": rule_id}