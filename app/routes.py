from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm


from typing import List
import bcrypt
import secrets
from bson.objectid import ObjectId


from app.auth import verificar_password, crear_token, get_current_user
from app.schemas import UsuarioOut,UsuarioIn, UsuarioUpdate, LoginIn, TokenOut, DispositivoIn, DispositivoOut, VariableIn
from app.db import get_db


router = APIRouter()


# Lista de usuarios creados
@router.get("/users", response_model=List[UsuarioOut])
async def obtener_usuarios():
    db = get_db()
    usuarios_cursor = db["usuarios"].find({})
    usuarios = []
    async for usuario in usuarios_cursor:
        usuarios.append({
            "id": str(usuario["_id"]),
            "username": usuario.get("username"),
            "email": usuario.get("email"),
            "name": usuario.get("name"),
            "country": usuario.get("country"),
            "city": usuario.get("city"),
            "company": usuario.get("company"),
            "rol": usuario.get("rol")
        })
    return usuarios

#creación de un usuario
@router.post("/users")
async def crear_usuario(usuario: UsuarioIn):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    # Verificar si el username ya existe
    if await db["usuarios"].find_one({"username": usuario.username}):
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    # Verificar si el correo ya existe
    if await db["usuarios"].find_one({"email": usuario.email}):
        raise HTTPException(status_code=400, detail="El correo electrónico ya está en uso")
    
    hashed_pw = bcrypt.hashpw(usuario.password.encode("utf-8"), bcrypt.gensalt())

    nuevo_usuario = {
        "username": usuario.username,
        "password": hashed_pw.decode("utf-8"),
        "email": usuario.email,
        "name": usuario.name,
        "country": usuario.country,
        "city": usuario.city,
        "company": usuario.company,
        "rol": usuario.rol
    }

    await db["usuarios"].insert_one(nuevo_usuario)

    token = crear_token({
    "           username": usuario.username,
                "emaiil": usuario.email,
                "rol": usuario.rol
                })

    return {"access_token": token, "token_type": "bearer"}

# eliminar un usuario
@router.delete("/users/{username}")
async def eliminar_usuario(username: str):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    resultado = await db["usuarios"].delete_one({"username": username})
    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return {"message": f"Usuario '{username}' eliminado correctamente"}

@router.patch("/users/{username}")
async def actualizar_usuario(username: str, datos: UsuarioUpdate):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    usuario = await db["usuarios"].find_one({"username": username})
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    actualizaciones = {}

    if datos.password:
        hashed_pw = bcrypt.hashpw(datos.password.encode("utf-8"), bcrypt.gensalt())
        actualizaciones["password"] = hashed_pw.decode("utf-8")

    if not actualizaciones:
        raise HTTPException(status_code=400, detail="No se proporcionaron datos para actualizar")

    await db["usuarios"].update_one(
        {"username": username},
        {"$set": actualizaciones}
    )

    return {"message": f"Usuario '{username}' actualizado correctamente"}

# iniciar sesion con un usuario (obtener un token)
@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    usuario = await db["usuarios"].find_one({"username": form_data.username})
    if not usuario:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    if not bcrypt.checkpw(form_data.password.encode("utf-8"), usuario["password"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    # Construir datos adicionales para el token
    token_data = {
        "username": usuario["username"],
        "rol": usuario.get("rol", "usuario")
    }

    token = crear_token(token_data)
    return {"access_token": token, "token_type": "bearer"}

# consultar el usuario logeado 
@router.get("/profile")
async def leer_perfil(usuario: dict = Depends(get_current_user)):
    return {
        "message": "Perfil accedido exitosamente",
        "usuario": usuario
    }


@router.post("/devices", response_model=DispositivoOut)
async def crear_dispositivo(
    dispositivo: DispositivoIn,
    user: dict = Depends(get_current_user)
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    # 1. Verificar si el dispositivo ya existe para este usuario
    existe = await db["dispositivos"].find_one({
        "device_id": dispositivo.device_id,
        "username": user["username"]
    })

    if existe:
        raise HTTPException(status_code=400, detail="El dispositivo ya existe para este usuario")

    # 2. Generar credenciales MQTT
    mqtt_username = f"dev_{dispositivo.device_id}"
    raw_mqtt_password = secrets.token_urlsafe(16)
    hashed = bcrypt.hashpw(raw_mqtt_password.encode(), bcrypt.gensalt()).decode()

    # 3. Insertar usuario MQTT
    await db["mqtt_user"].insert_one({
        "username": mqtt_username,
        "password": hashed
    })
    
    # 3. Crear ACL para publicación y suscripción en cualquier subtopic
    topic_acl = {
        "username": mqtt_username,
        "pubsub": [
            f"iot/{user['username']}/{dispositivo.device_id}/#"
        ]
    }

    # 4. Insertar en colección ACL
    await db["mqtt_acl"].insert_one(topic_acl)

    # 4. Registrar el dispositivo
    nuevo_dispositivo = {
        "name": dispositivo.name,
        "device_id": dispositivo.device_id,
        "username": user["username"],
        "mqtt_username": mqtt_username
    }
    res = await db["dispositivos"].insert_one(nuevo_dispositivo)

    # 5. Preparar respuesta
    out = DispositivoOut(
        id=str(res.inserted_id),
        name=dispositivo.name,
        device_id=dispositivo.device_id,
        username=user["username"],
        mqtt_username=mqtt_username,
        mqtt_password=raw_mqtt_password
    )
    return out

# consultar dispositivos
@router.get("/devices")
async def obtener_dispositivos(user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    devices_cursor = db["dispositivos"].find({"username": user["username"]})
    devices = []
    async for device in devices_cursor:
        devices.append({
            "id": str(device["_id"]),
            "device_id": device.get("device_id"),
            "name": device.get("name"),
            "username": device.get("username")
        })
    return devices

# borrar un dispositivo
@router.delete("/devices/{device_id}")
async def device_delete(device_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    resultado = await db["dispositivos"].delete_one({
        "device_id": device_id,
        "username": user["username"]
    })

    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    return {"message": f"Dispositivo '{device_id}' eliminado correctamente"}

# crear una variable
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

    nueva_variable = {
        "device_id": variable.device_id,
        "username": user["username"],
        "variable_name": variable.variable_name,
        "unit": variable.unit,
        "description": variable.description,
        "sampling_ms":variable.sampling_ms
    }

    await db["variables"].insert_one(nueva_variable)
    return {"message": "Variable registrada correctamente"}

@router.get("/variables")
async def obtener_dispositivos(user: dict = Depends(get_current_user)):
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