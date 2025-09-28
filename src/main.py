# src/main.py

import json
import asyncio
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings, log
from src.models.chat_models import ChatRequest, ChatMessage
from src.modules import pse_client, gemini_client, rag_client, firestore_client
from src.core.prompts import PIDA_SYSTEM_PROMPT
from src.core.security import get_current_user_id
from typing import List, Dict, Any

app = FastAPI(
    title="PIDA Backend API - Logic Only",
    description="API para el asistente jurídico PIDA, con persistencia en BD y autenticación."
)

# --- CONFIGURACIÓN DE CORS ---
origins = [
    "https://pida.iiresodh.org",
    "https://pida-ai.com",
    "http://localhost",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    # --- LA ÚNICA CORRECCIÓN ESTÁ EN LA SIGUIENTE LÍNEA ---
    allow_methods=["POST", "GET", "DELETE", "PATCH"],
    allow_headers=["*"],
)

# --- LÓGICA DE STREAMING (MODIFICADA) ---
async def stream_chat_response_generator(chat_request: ChatRequest, country_code: str | None, user_id: str, convo_id: str):
    def create_sse_event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    try:
        # Guarda el mensaje del usuario en la BD ANTES de procesar
        user_message = ChatMessage(role="user", content=chat_request.prompt)
        await firestore_client.add_message_to_conversation(user_id, convo_id, user_message)

        # 1. Inicia el proceso
        yield create_sse_event({"event": "status", "message": "Iniciando... 🕵️"})
        await asyncio.sleep(0.5)

        # 2. Carga el historial desde Firestore para dar contexto al modelo
        log.info(f"Cargando historial para la convo {convo_id} del usuario {user_id}")
        history_from_db = await firestore_client.get_conversation_messages(user_id, convo_id)
        # Excluimos el último mensaje que acabamos de añadir para no duplicarlo en el historial de contexto
        history_for_gemini = gemini_client.prepare_history_for_vertex(history_from_db[:-1])

        # 3. Emite los pasos de la búsqueda
        log.info(f"Iniciando búsqueda de fuentes (PSE y RAG) para prompt: '{chat_request.prompt[:50]}...'")
        yield create_sse_event({"event": "status", "message": "Consultando jurisprudencia y fuentes externas..."})
        
        search_tasks = [
            pse_client.search_for_sources(chat_request.prompt, num_results=3),
            rag_client.search_internal_documents(chat_request.prompt)
        ]
        
        # 4. Procesa tareas y notifica sobre el progreso
        combined_context = ""
        task_count = len(search_tasks)
        for i, task in enumerate(asyncio.as_completed(search_tasks)):
            result = await task
            combined_context += result
            yield create_sse_event({"event": "status", "message": f"Fuente de contexto ({i+1}/{task_count}) procesada..."})
        
        await asyncio.sleep(0.5)
        yield create_sse_event({"event": "status", "message": "Contexto recopilado. Construyendo la consulta..."})
        
        # 5. Construye el prompt final y llama a Gemini
        final_prompt = f"Contexto geográfico: {country_code}\n{combined_context}\n\n---\n\nPregunta del usuario: {chat_request.prompt}"
        yield create_sse_event({"event": "status", "message": f"Enviando a {settings.GEMINI_MODEL} para análisis... 🧠"})
        
        full_response_text = ""
        async for chunk in gemini_client.generate_streaming_response(
            system_prompt=PIDA_SYSTEM_PROMPT,
            prompt=final_prompt,
            history=history_for_gemini
        ):
            yield create_sse_event({'text': chunk})
            full_response_text += chunk

        # 6. Guarda la respuesta completa del modelo en la BD
        if full_response_text:
            model_message = ChatMessage(role="model", content=full_response_text)
            await firestore_client.add_message_to_conversation(user_id, convo_id, model_message)

        # 7. Finaliza el stream
        log.info(f"Streaming finalizado para convo {convo_id}. Enviando evento 'done'.")
        yield create_sse_event({'event': 'done'})

    except Exception as e:
        log.error(f"Error crítico durante el streaming para convo {convo_id}: {e}", exc_info=True)
        error_message = json.dumps({"error": "Lo siento, ocurrió un error interno al generar la respuesta."})
        yield f"data: {error_message}\n\n"

# --- ENDPOINTS DE LA API ---

@app.get("/status", tags=["Status"])
def read_status():
    return {"status": "ok", "message": "PIDA Backend de Lógica funcionando."}

# --- NUEVOS ENDPOINTS PARA GESTIONAR CONVERSACIONES ---

@app.get("/conversations", response_model=List[Dict[str, Any]], tags=["Chat History"])
async def get_user_conversations(user_id: str = Depends(get_current_user_id)):
    """Obtiene la lista de todas las conversaciones para el usuario autenticado."""
    return await firestore_client.get_conversations(user_id)

@app.get("/conversations/{convo_id}/messages", response_model=List[ChatMessage], tags=["Chat History"])
async def get_conversation_details(convo_id: str, user_id: str = Depends(get_current_user_id)):
    """Obtiene todos los mensajes de una conversación específica."""
    return await firestore_client.get_conversation_messages(user_id, convo_id)

@app.post("/conversations", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED, tags=["Chat History"])
async def create_new_empty_conversation(request: Request, user_id: str = Depends(get_current_user_id)):
    """Crea una nueva conversación vacía y devuelve su ID y título."""
    body = await request.json()
    title = body.get("title", "Nuevo Chat")
    if not title:
        raise HTTPException(status_code=400, detail="El título no puede estar vacío")
    new_convo = await firestore_client.create_new_conversation(user_id, title)
    return new_convo

@app.delete("/conversations/{convo_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Chat History"])
async def delete_a_conversation(convo_id: str, user_id: str = Depends(get_current_user_id)):
    """Elimina una conversación y todos sus mensajes."""
    await firestore_client.delete_conversation(user_id, convo_id)
    return

@app.patch("/conversations/{convo_id}/title", status_code=status.HTTP_204_NO_CONTENT, tags=["Chat History"])
async def update_conversation_title_handler(
    convo_id: str, 
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    """Actualiza el título de una conversación."""
    body = await request.json()
    new_title = body.get("title")
    if not new_title:
        raise HTTPException(status_code=400, detail="El título no puede estar vacío")
    await firestore_client.update_conversation_title(user_id, convo_id, new_title)
    return

# --- ENDPOINT DE CHAT MODIFICADO ---

@app.post("/chat-stream/{convo_id}", tags=["Chat"])
async def chat_stream_handler(
    convo_id: str,
    chat_request: ChatRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    """Maneja el streaming de una conversación existente."""
    country_code = request.headers.get('X-Country-Code', None)
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(
        stream_chat_response_generator(chat_request, country_code, user_id, convo_id),
        headers=headers
    )
