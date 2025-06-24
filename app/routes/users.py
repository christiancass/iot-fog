from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm


from typing import List
import bcrypt
import secrets
from bson.objectid import ObjectId


from app.routes.auth import verificar_password, crear_token, get_current_user
from app.routes.schemas import UsuarioOut,UsuarioIn, UsuarioUpdate, LoginIn, TokenOut, DispositivoIn, DispositivoOut, VariableIn
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

# actualizar datos de un usuario
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
