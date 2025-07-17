from pydantic import BaseModel, Field
from typing import Optional, Union, Any, List, Optional, Dict
from datetime import datetime 


class UsuarioIn(BaseModel):
    username: str
    password: str
    email: str
    name: str
    country: str
    city: str
    company: Optional[str]= None
    rol: Optional[str]="usuario"

class UsuarioOut(BaseModel):
    id: str
    username: str
    email: str
    name: str
    country: str
    city: str
    company: Optional[str] = None
    rol: Optional[str] = "usuario"


class UsuarioUpdate(BaseModel):
    password: Optional[str] = Field(None, min_length=6)
    
class LoginIn(BaseModel):
    email: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DispositivoIn(BaseModel):
    name: str
    device_id: str

class DispositivoOut(BaseModel):
    id: str
    name: str
    device_id: str
    username: str
    mqtt_username: str
    mqtt_password: str


class StoreFlag(BaseModel):
    store_in_mongo: bool

class VariableIn(BaseModel):
    device_id: str
    variable_name: str
    unit: str
    description:str
    sampling_ms:str

class MqttMessage(BaseModel):
    topic: str
    payload: Any
    timestamp: datetime


class AlarmRuleIn(BaseModel):
    device_id: str = Field(..., description="ID del dispositivo")
    variable_name: str = Field(..., description="Nombre de la variable a monitorear")
    field: str = Field("value", description="Campo de payload a evaluar")
    operator: str = Field(">", description="Operador de comparación: >, <, >=, <=, =, !=")
    threshold: float = Field(..., description="Valor umbral para la condición")
    window_s: Optional[int] = Field(
        None,
        description="Tamaño de la ventana en segundos (si None → regla instantánea)"
    )

class AlarmRuleOut(BaseModel):
    rule_id: str = Field(..., description="ID de la regla creada en EMQX")


class PanelConfig(BaseModel):
    type: str
    title: str
    flux: str            # p.ej. "mean()" o "last()" o "limit(n:50)"
    gridPos: Dict = None

class DashboardConfig(BaseModel):
    title: str
    range: str           # p.ej. "-1h", "-6h"
    bucket: str          # p.ej. "measurements"
    measurement: str     # "iot_data"
    field: str = "value" # filtro de campo
    tagFilters: Dict[str,str]  # debe contener device_id, username, variable_id
    panels: List[PanelConfig]

class DashboardResponse(BaseModel):
    url: str