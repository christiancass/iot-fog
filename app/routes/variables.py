from fastapi import APIRouter, HTTPException, Depends
from app.routes.auth import get_current_user
from app.models.schemas import VariableIn
from app.utils.db import get_db

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

    # Validar si ya existe una variable con el mismo variable_name y device_id para este usuario
    variable_existente = await db["variables"].find_one({
        "device_id": variable.device_id,
        "variable_name": variable.variable_name,
        "username": user["username"]
    })

    if variable_existente:
        raise HTTPException(status_code=400, detail="Ya existe una variable con ese nombre para el mismo dispositivo")

    # Insertar la nueva variable
    nueva_variable = {
        "device_id": variable.device_id,
        "username": user["username"],
        "variable_name": variable.variable_name,
        "unit": variable.unit,
        "description": variable.description,
        "sampling_ms": variable.sampling_ms
    }

    await db["variables"].insert_one(nueva_variable)
    return {"message": "Variable registrada correctamente"}

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
            "device_id": variable.get("device_id"),
            "variable_name": variable.get("variable_name"),
            "unit": variable.get("unit"),
            "description": variable.get("description"),
            "sampling_ms": variable.get("sampling_ms"),
            "username": variable.get("username")
        })
    return variables

