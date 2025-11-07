from fastapi import APIRouter, HTTPException, Depends
from app.routes.auth import get_current_user
from app.models.schemas import VariableIn
from app.utils.db import get_db
from app.apis.emqx_api import emqx_delete
import logging

router = APIRouter()

# Crear una variable
@router.post("/variables")
async def agregar_variable(variable: VariableIn, user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    # Validar que el dispositivo existe y pertenece al usuario autenticado
    dispositivo = await db["dispositivos"].find_one({
        "device_id": variable.device_id,
        "username": user["username"]
    })
    if not dispositivo:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado o no autorizado")

    # Validar duplicados por variable_id
    variable_id_existente = await db["variables"].find_one({
        "variable_id": variable.variable_id,
        "username": user["username"],
        "device_id": variable.device_id
    })
    if variable_id_existente:
        raise HTTPException(status_code=400, detail="Ya existe una variable con ese variable_id para este dispositivo")

    # Validar duplicados por nombre
    variable_nombre_existente = await db["variables"].find_one({
        "device_id": variable.device_id,
        "variable_name": variable.variable_name,
        "username": user["username"]
    })
    if variable_nombre_existente:
        raise HTTPException(status_code=400, detail="Ya existe una variable con ese nombre para el mismo dispositivo")

    # Construir topic automáticamente
    topic = f"iot/{user['username']}/{variable.device_id}/{variable.variable_id}/sdata"

    # Insertar la nueva variable
    nueva_variable = {
        "variable_id": variable.variable_id,
        "device_id": variable.device_id,
        "username": user["username"],
        "variable_name": variable.variable_name,
        "unit": variable.unit,
        "topic": topic,
        "sampling_ms": variable.sampling_ms
    }

    await db["variables"].insert_one(nueva_variable)
    logging.info(f"[create] Variable '{variable.variable_name}' registrada con topic '{topic}'")
    return {"message": "Variable registrada correctamente", "topic": topic}


# Obtener todas las variables del usuario autenticado
@router.get("/variables")
async def obtener_variables(user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    variables_cursor = db["variables"].find({"username": user["username"]})
    variables = []
    async for variable in variables_cursor:
        variables.append({
            "id": str(variable["_id"]),
            "variable_id": variable.get("variable_id"),
            "device_id": variable.get("device_id"),
            "variable_name": variable.get("variable_name"),
            "unit": variable.get("unit"),
            "topic": variable.get("topic"),
            "sampling_ms": variable.get("sampling_ms"),
            "username": variable.get("username")
        })
    return variables


# Eliminar una variable
@router.delete("/variables/{variable_id}")
async def eliminar_variable(variable_id: str, user: dict = Depends(get_current_user)):
    """
    Elimina una variable identificada por variable_id y asociada al usuario actual.
    - Borra primero en EMQX las reglas SAVE y ALARMAS relacionadas a esa variable.
    - Luego borra los registros en Mongo (emqx_save_rules, alarmas, variables).
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    # 1) Validar que la variable exista
    variable = await db["variables"].find_one({
        "variable_id": variable_id,
        "username": user["username"]
    })
    if not variable:
        raise HTTPException(status_code=404, detail="Variable no encontrada o no pertenece al usuario")

    device_id = variable.get("device_id")

    # 2) Eliminar reglas SAVE en EMQX
    async for rule in db["emqx_save_rules"].find({
        "device_id": device_id,
        "variable_id": variable_id,
        "username": user["username"]
    }):
        rule_id = rule.get("rule_id")
        if rule_id:
            try:
                await emqx_delete(f"/rules/{rule_id}")
                logging.info(f"[delete] Regla save-rule EMQX {rule_id} eliminada para variable {variable_id}")
            except Exception as e:
                logging.warning(f"[delete] Error eliminando save-rule EMQX {rule_id}: {e!r}")

    # 3) Eliminar reglas de ALARMAS en EMQX
    async for alarma in db["alarmas"].find({
        "device_id": device_id,
        "variable_id": variable_id,
        "username": user["username"]
    }):
        rule_id = alarma.get("rule_id")
        if rule_id:
            try:
                await emqx_delete(f"/rules/{rule_id}")
                logging.info(f"[delete] Regla de alarma EMQX {rule_id} eliminada para variable {variable_id}")
            except Exception as e:
                logging.warning(f"[delete] Error eliminando regla de alarma EMQX {rule_id}: {e!r}")

    # 4) Borrar reglas SAVE y ALARMAS en Mongo
    await db["emqx_save_rules"].delete_many({
        "device_id": device_id,
        "variable_id": variable_id,
        "username": user["username"]
    })
    await db["alarmas"].delete_many({
        "device_id": device_id,
        "variable_id": variable_id,
        "username": user["username"]
    })

    # 5) Borrar la VARIABLE
    result = await db["variables"].delete_one({
        "variable_id": variable_id,
        "username": user["username"]
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No se pudo eliminar la variable")

    logging.info(f"[delete] Variable '{variable.get('variable_name')}' (variable_id={variable_id}) eliminada correctamente")
    return {"message": f"Variable '{variable.get('variable_name')}' eliminada correctamente"}
