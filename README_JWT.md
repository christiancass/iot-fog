# Autenticación JWT con FastAPI

Este documento describe la implementación de autenticación basada en JWT (JSON Web Token) en una aplicación FastAPI.

---

## 🔑 Objetivo

Proteger rutas de la API utilizando JWT para identificar y autenticar usuarios, permitiendo el acceso solo a usuarios que tengan un token válido.

---

## 🔧 Instalación de dependencias

Asegúrate de tener en `requirements.txt`:

```txt
python-jose[cryptography]
passlib[bcrypt]
python-multipart
```

Instálalas:

```bash
pip install -r requirements.txt
```

---

## 🔒 Estructura JWT

El token contiene información del usuario y una fecha de expiración. Se genera con (crear un archivo auth.py):

```python
# app/auth.py
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

# Clave secreta y configuración
SECRET_KEY = "clave super secreta"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60*24*30

# Encriptación
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Funciones de autenticación
def verificar_password(password_plano, password_hash):
    return pwd_context.verify(password_plano, password_hash)

def generar_hash(password):
    return pwd_context.hash(password)

def crear_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verificar_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
```

### Datos comunes incluidos:

```python
{
    "sub": "username",
    "email": "...",
    "rol": "...",
    "exp": "..."
}
```

---

## 🌐 Endpoint para obtener token y login

```python
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm


from typing import List
import bcrypt
from bson.objectid import ObjectId


from app.auth import verificar_password, crear_token, get_current_user
from app.schemas import UsuarioOut,UsuarioIn, UsuarioUpdate, LoginIn, TokenOut 
from app.db import get_db

router = APIRouter()



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
```

---

## 🔓 Protección de rutas

### Dependencia:

```python
# Dependencia para proteger rutas
#app/auth.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = verificar_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return payload
```

### Ruta protegida:

```python
@router.get("/perfil")
async def leer_perfil(usuario: dict = Depends(get_current_user)):
    return {
        "message": "Perfil accedido exitosamente",
        "usuario": usuario
    }
```

---

## 🎨 Uso en Postman

1. Obtener token:

   * `POST` a `/login` usando `x-www-form-urlencoded`
   * Campos: `username`, `password`

2. Usar token:

   * Pestaña `Authorization`
   * Tipo: `Bearer Token`
   * Pegar el `access_token` recibido


---

## 📈 Resultados esperados

* Acceso exitoso a rutas protegidas con token válido.
* Error `401` con token inválido o ausente.
* Login devuelve `access_token` JWT con información personalizada.

---

## 📢 Recomendaciones

* No expongas `SECRET_KEY` en el código.
* Aumenta el tiempo de expiración solo si es necesario.
* Considera refrescar tokens si quieres sesiones largas.
* Usa HTTPS siempre que trabajes con autenticación.

---

✅ Implementación JWT exitosa y segura con FastAPI.
