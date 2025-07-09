from fastapi import APIRouter, HTTPException, Depends


from typing import List
import bcrypt


from app.models.schemas import UsuarioOut,UsuarioIn, UsuarioUpdate
from app.utils.db import get_db
from app.routes.auth import get_current_user

router = APIRouter()

# Obtener solo la información del usuario autenticado
@router.get("/users", response_model=UsuarioOut)
async def obtener_usuario_actual(user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(500, "Base de datos no inicializada")

    usuario = await db["usuarios"].find_one({"username": user["username"]})
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")

    return {
        "id": str(usuario["_id"]),
        "username": usuario.get("username"),
        "email": usuario.get("email"),
        "name": usuario.get("name"),
        "country": usuario.get("country"),
        "city": usuario.get("city"),
        "company": usuario.get("company"),
        "rol": usuario.get("rol")
    }


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
    return {"Usuario creado con exito"}

# Eliminar un usuario (solo si está autenticado)
@router.delete("/users/{username}")
async def eliminar_usuario(username: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    # (Opcional) Validar que el usuario autenticado solo pueda eliminar su propio usuario
    if username != user["username"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar este usuario")

    resultado = await db["usuarios"].delete_one({"username": username})
    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return {"message": f"Usuario '{username}' eliminado correctamente"}


# Actualizar datos de un usuario (solo si está autenticado)
@router.patch("/users/{username}")
async def actualizar_usuario(
    username: str,
    datos: UsuarioUpdate,
    user: dict = Depends(get_current_user)
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Base de datos no inicializada")

    # Validar que el usuario autenticado solo pueda actualizar su propia cuenta
    if username != user["username"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para modificar este usuario")

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
