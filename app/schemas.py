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
    
