# Microservicio de Autenticación con FastAPI, MongoDB y Docker

Este proyecto implementa un microservicio de autenticación básica utilizando FastAPI, MongoDB (con Motor para acceso asíncrono), y Docker. Proporciona endpoints para crear, consultar, actualizar y eliminar usuarios.

---

## 🧰 Tecnologías Usadas

- FastAPI
- MongoDB (vía Motor)
- Docker & Docker Compose
- bcrypt (para el hashing de contraseñas)
- Pydantic

---

## 📁 Estructura del Proyecto

```
.
├── app/
│   ├── main.py
│   ├── db.py
│   ├── routes.py
│   └── schemas.py
├── Dockerfile
├── requirements.txt
├── docker-compose.yml
└── .env
```

---

## ⚙️ Configuración del Entorno

### Archivo `.env`
```env
MONGO_HOST=mongodb
MONGO_PORT=27017
MONGO_USER=root
MONGO_PASS=example
```

### `docker-compose.yml`
```yaml
version: "3.9"

services:
  api:
    build: .
    container_name: fastapi-auth
    ports:
      - "8000:8000"
    depends_on:
      - mongo
    networks:
      - red-auth

  mongo:
    image: mongo:5.0
    container_name: auth-mongo
    restart: always
    volumes:
      - auth-mongo-data:/data/db
    environment:
      MONGO_INITDB_ROOT_USERNAME: root
      MONGO_INITDB_ROOT_PASSWORD: example
    networks:
      - red-auth

  mongo-express:
    image: mongo-express
    container_name: mongo-express
    restart: always
    ports:
      - "8081:8081"
    environment:
      ME_CONFIG_MONGODB_SERVER: mongo
      ME_CONFIG_MONGODB_ADMINUSERNAME: root
      ME_CONFIG_MONGODB_ADMINPASSWORD: example
      ME_CONFIG_BASICAUTH_USERNAME: admin
      ME_CONFIG_BASICAUTH_PASSWORD: admin
    depends_on:
      - mongo
    networks:
      - red-auth

  emqx:
    image: emqx/emqx:latest
    container_name: emqx
    ports:
      - "1883:1883"
      - "8083:8083"
      - "18083:18083"
    environment:
      - EMQX_DASHBOARD__DEFAULT_USER__PASSWORD=admin123
    volumes:
      - emqx-data:/opt/emqx/data
      - emqx-log:/opt/emqx/log
    networks:
      - red-auth

volumes:
  auth-mongo-data:
  emqx-data:
  emqx-log:

networks:
  red-auth:

```

### `Dockerfile`
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### `requirements.txt`
```text
fastapi
uvicorn
motor
python-dotenv
bcrypt
```

---

## 🧠 Código Fuente

### `app/main.py`
```python
from fastapi import FastAPI
from app.db import connect_to_mongo, close_mongo_connection
from app.routes import router

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

app.include_router(router)

```

---

### `app/db.py`
```python
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
import os

client = None
db = None

async def connect_to_mongo():
    global client, db
    mongo_user = os.getenv("MONGO_USER", "root")
    mongo_pass = os.getenv("MONGO_PASS", "example")
    mongo_host = os.getenv("MONGO_HOST", "mongo")
    mongo_port = int(os.getenv("MONGO_PORT", 27017))
    mongo_db = os.getenv("MONGO_DB", "iot")

    uri = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/admin"

    try:
        client = AsyncIOMotorClient(uri)
        db = client[mongo_db]
        print("✅ Conectado a MongoDB con Motor")
    except PyMongoError as e:
        print("❌ Error de conexión a MongoDB:", e)

async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("🔌 Conexión a MongoDB cerrada")

def get_db():
    global db
    return db
```

---

### `app/schemas.py`
```python
from pydantic import BaseModel, Field
from typing import Optional


class UsuarioIn(BaseModel):
    username: str
    password: str

class UsuarioOut(BaseModel):
    id: str
    username: str

class UsuarioUpdate(BaseModel):
    password: Optional[str] = Field(None, min_length=6)
    
```

---

### `app/routes.py`
```python
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
```

---

## 🚀 Cómo ejecutar el microservicio

1. Clona este repositorio y navega al directorio.
2. Crea un archivo `.env` como el mostrado arriba.
3. Ejecuta:

```bash
docker-compose up --build
```

4. Usa Postman para probar los endpoints en `http://localhost:8000`.

---

## 📬 Endpoints Disponibles

| Método | Ruta               | Descripción                      |
|--------|--------------------|----------------------------------|
| POST   | /usuarios          | Crear nuevo usuario              |
| GET    | /usuarios          | Listar todos los usuarios        |
| PATCH  | /usuarios/{usuario}| Actualizar la contraseña         |
| DELETE | /usuarios/{usuario}| Eliminar un usuario              |

---

## 📌 Notas Finales

- No se implementa JWT ni sesiones. Este microservicio es un ejemplo funcional de CRUD de autenticación.
- Requiere protección adicional para producción (ej. CORS, validaciones, tokens, roles).
