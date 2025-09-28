# src/models/chat_models.py

from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class ChatMessage(BaseModel):
    role: Literal["user", "model"]
    content: str

class ChatRequest(BaseModel):
    prompt: str
    history: List[ChatMessage] = []
    user_id: str = Field(..., description="El ID del usuario de WordPress.")
    conversation_id: Optional[str] = Field(None, description="El ID de la conversación a continuar.")
