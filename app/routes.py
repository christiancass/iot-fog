from fastapi import APIRouter, HTTPException
from typing import List
import bcrypt
from bson.objectid import ObjectId

from app.schemas import UsuarioOut,UsuarioIn, UsuarioUpdate 
from app.db import get_db


router = APIRouter()


@router.get("/usuarios", response_model=List[UsuarioOut])
async def obtener_usuarios():
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    usuarios_cursor = db["usuarios"].find({})
    usuarios = []
    async for usuario in usuarios_cursor:
        usuarios.append({
            "id": str(usuario["_id"]),
            "username": usuario["username"]
        })
    return usuarios

@router.post("/usuarios")
async def crear_usuario(usuario: UsuarioIn):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    if await db["usuarios"].find_one({"username": usuario.username}):
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    
    hashed_pw = bcrypt.hashpw(usuario.password.encode("utf-8"), bcrypt.gensalt())
    
    nuevo_usuario = {
        "username": usuario.username,
        "password": hashed_pw.decode("utf-8")
    }

    await db["usuarios"].insert_one(nuevo_usuario)
    return {"message": "Usuario creado correctamente"}

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