from pydantic import BaseModel, Field
from typing import Optional, Union
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
    device_id: str
    name: str
    username: str

class VariableIn(BaseModel):
    device_id: str
    variable_name: str
    unit: str
    description:str
    sampling_ms:str

