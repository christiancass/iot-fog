from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm


from typing import List
import bcrypt
import secrets
from bson.objectid import ObjectId


from app.routes.auth import verificar_password, crear_token, get_current_user
from app.models.schemas import UsuarioOut,UsuarioIn, UsuarioUpdate, LoginIn, TokenOut, DispositivoIn, DispositivoOut, VariableIn
from app.utils.db import get_db


router = APIRouter()


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
