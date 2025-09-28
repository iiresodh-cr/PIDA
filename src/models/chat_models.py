# src/models/chat_models.py

from pydantic import BaseModel
from typing import List, Literal

class ChatMessage(BaseModel):
    """Representa un único mensaje en el historial de chat."""
    role: Literal["user", "model"]
    content: str

class ChatRequest(BaseModel):
    """El cuerpo de la petición para el endpoint /chat."""
    prompt: str
    history: List[ChatMessage] = [] # Por defecto, una lista vacía para retrocompatibilidad (prueba)
