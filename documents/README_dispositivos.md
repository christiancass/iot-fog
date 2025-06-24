
# 📟 Gestión de Dispositivos - API FastAPI

Este módulo permite a los usuarios autenticados gestionar dispositivos (por ejemplo, sensores o actuadores) ligados a su cuenta. Cada dispositivo está asociado a un `username` mediante el token JWT generado al iniciar sesión.

---

## 📌 Requisitos previos

- Haber creado y autenticado un usuario con JWT.
- Incluir el token JWT en el encabezado de las peticiones protegidas:

```http
Authorization: Bearer <token>
```

---

## 📁 Estructura de modelo - `Dispositivo`

### 🔹 `schemas.py`

```python
from pydantic import BaseModel
from typing import Optional

class DispositivoIn(BaseModel):
    name: str
    device_id: str

class DispositivoOut(BaseModel):
    id: str
    device_id: str
    name: str
    username: str
```

---

## 🔧 Crear dispositivo
```python

@router.post("/new_device")
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
```

### 🔹 Endpoint

```http
POST /devices
```

### 🔹 Headers

```http
Authorization: Bearer <token>
Content-Type: application/json
```

### 🔹 Body (JSON)

```json
{
  "name": "sensor_temperatura_1",
  "device_id": "device001"
}
```

### 🔹 Respuesta

```json
{
  "message": "Dispositivo creado exitosamente"
}
```

---

## 📋 Listar dispositivos
```python
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
```


### 🔹 Endpoint

```http
GET /device_list
```

### 🔹 Headers

```http
Authorization: Bearer <token>
```

### 🔹 Respuesta

```json
[
  {
    "id": "64fd245ed75d1c12a3df45b2",
    "device_id": "device001",
    "name": "sensor_temperatura_1",
    "username": "usuario1"
  }
]
```

---

## ❌ Eliminar dispositivo

### 🔹 Endpoint

```http
DELETE /device/{name}
```

### 🔹 Headers

```http
Authorization: Bearer <token>
```

### 🔹 Ejemplo

```http
DELETE /device/sensor_temperatura_1
```

### 🔹 Respuesta

```json
{
  "message": "Dispositivo 'sensor_temperatura_1' eliminado correctamente"
}
```

---

## 🛡️ Seguridad

- Cada usuario solo puede ver, crear o eliminar sus propios dispositivos.
- El campo `username` se extrae automáticamente del token JWT en cada operación protegida.

---

## ✅ Consideraciones

- Si se intenta crear un dispositivo con un `device_id` ya existente para el mismo usuario, se devolverá un error 400.
- Si se intenta eliminar un dispositivo que no existe o que no pertenece al usuario autenticado, se devolverá un error 404.

---
