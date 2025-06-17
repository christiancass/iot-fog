from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm


from typing import List
import bcrypt
from bson.objectid import ObjectId


from app.auth import verificar_password, crear_token, get_current_user
from app.schemas import UsuarioOut,UsuarioIn, UsuarioUpdate, LoginIn, TokenOut, DispositivoIn, DispositivoOut 
from app.db import get_db


router = APIRouter()


@router.get("/usuarios", response_model=List[UsuarioOut])
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


@router.post("/usuarios")
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


@router.delete("/usuarios/{username}")
async def eliminar_usuario(username: str):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    resultado = await db["usuarios"].delete_one({"username": username})
    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return {"message": f"Usuario '{username}' eliminado correctamente"}

@router.patch("/usuarios/{username}")
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


@router.get("/perfil")
async def leer_perfil(usuario: dict = Depends(get_current_user)):
    return {
        "message": "Perfil accedido exitosamente",
        "usuario": usuario
    }


@router.post("/dispositivos")
async def crear_dispositivo(dispositivo: DispositivoIn, user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    existe = await db["dispositivos"].find_one({
        "device_id": dispositivo.device_id,
        "username": user["username"]
    })

    if existe:
        raise HTTPException(status_code=400, detail="El dispositivo ya existe para este usuario")

    nuevo_dispositivo = {
        "device_id": dispositivo.device_id,
        "name": dispositivo.name,
        "username": user["username"]
    }

    await db["dispositivos"].insert_one(nuevo_dispositivo)
    return {"message": "Dispositivo creado correctamente"}
