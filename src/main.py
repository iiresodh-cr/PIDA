# src/main.py

import json
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings, log
from src.models.chat_models import ChatRequest
# Asegúrate de que firestore_client esté importado
from src.modules import pse_client, gemini_client, rag_client, firestore_client
from src.core.prompts import PIDA_SYSTEM_PROMPT

app = FastAPI(
    title="PIDA Backend API con Firestore",
    description="API para el asistente jurídico PIDA, con persistencia en Firestore y endpoints completos."
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
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# --- LÓGICA DE STREAMING CON FIRESTORE ---
async def stream_chat_response_generator(chat_request: ChatRequest, country_code: str | None):
    def create_sse_event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    try:
        # 1. OBTENER O CREAR CONVERSACIÓN EN FIRESTORE
        conversation = await firestore_client.get_or_create_conversation(chat_request.user_id, chat_request.conversation_id)
        current_convo_id = conversation["id"]
        
        # Devuelve el ID de la conversación al cliente para que lo guarde
        yield create_sse_event({"event": "conversation_id", "id": current_convo_id})

        # 2. GUARDAR EL MENSAJE DEL USUARIO
        await firestore_client.add_message_to_conversation(
            user_id=chat_request.user_id,
            conversation_id=current_convo_id,
            role="user",
            content=chat_request.prompt
        )

        # 3. ACTUALIZAR TÍTULO SI ES LA PRIMERA PREGUNTA DE UN NUEVO CHAT
        if conversation.get('title') == 'Nuevo Chat':
            # Genera un título corto a partir de las primeras palabras del prompt
            new_title = ' '.join(chat_request.prompt.split(' ')[0:5])
            if len(chat_request.prompt.split(' ')) > 5:
                new_title += '...'
            await firestore_client.update_conversation_title(chat_request.user_id, current_convo_id, new_title)

        # 4. BÚSQUEDA DE FUENTES (sin cambios)
        yield create_sse_event({"event": "status", "message": "Iniciando búsqueda de fuentes..."})
        search_tasks = [
            pse_client.search_for_sources(chat_request.prompt, num_results=3),
            rag_client.search_internal_documents(chat_request.prompt)
        ]
        
        combined_context = ""
        for task in asyncio.as_completed(search_tasks):
            result = await task
            combined_context += result
            yield create_sse_event({"event": "status", "message": "Contexto encontrado. Procesando..."})

        # 5. OBTENER HISTORIAL DESDE FIRESTORE PARA ENVIAR A GEMINI
        history_from_db = await firestore_client.get_conversation_history(chat_request.user_id, current_convo_id)
        
        # Quitamos el último mensaje (el que acaba de enviar el usuario) para no duplicarlo
        history_for_gemini_pydantic = history_from_db[:-1]

        final_prompt = f"Contexto geográfico: {country_code}\n{combined_context}\n\n---\n\nPregunta del usuario: {chat_request.prompt}"
        history_for_vertex = gemini_client.prepare_history_for_vertex(history_for_gemini_pydantic)
        
        yield create_sse_event({"event": "status", "message": "Generando análisis jurídico..."})

        # 6. INICIAR STREAMING DE GEMINI Y GUARDAR RESPUESTA
        full_response_text = ""
        async for chunk in gemini_client.generate_streaming_response(
            system_prompt=PIDA_SYSTEM_PROMPT,
            prompt=final_prompt,
            history=history_for_vertex
        ):
            full_response_text += chunk
            yield create_sse_event({'text': chunk})

        # 7. GUARDAR RESPUESTA COMPLETA DEL MODELO
        await firestore_client.add_message_to_conversation(
            user_id=chat_request.user_id,
            conversation_id=current_convo_id,
            role="model",
            content=full_response_text
        )

        log.info("Streaming finalizado. Respuesta del modelo guardada.")
        yield create_sse_event({'event': 'done'})

    except Exception as e:
        log.error(f"Error crítico durante el proceso de streaming: {e}", exc_info=True)
        error_message = json.dumps({"error": "Lo siento, ocurrió un error interno al generar la respuesta."})
        yield f"data: {error_message}\n\n"


# --- ENDPOINTS DE LA API ---

@app.get("/status", tags=["Status"])
def read_status():
    return {"status": "ok", "message": "PIDA Backend con Firestore funcionando."}

# ENDPOINT para obtener la lista de conversaciones
@app.get("/conversations/{user_id}", tags=["Conversations"])
async def get_conversations(user_id: str):
    """Obtiene la lista de todas las conversaciones para un usuario específico."""
    try:
        conversations = await firestore_client.get_user_conversations(user_id)
        return conversations
    except Exception as e:
        log.error(f"Error al obtener conversaciones para el usuario {user_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron obtener las conversaciones.")

# NUEVO ENDPOINT para obtener los mensajes de un chat específico
@app.get("/conversations/{user_id}/{conversation_id}", tags=["Conversations"])
async def get_conversation_messages(user_id: str, conversation_id: str):
    """Obtiene todos los mensajes de una conversación específica."""
    try:
        messages = await firestore_client.get_conversation_history(user_id, conversation_id)
        return messages
    except Exception as e:
        log.error(f"Error al obtener mensajes para la conversación {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron obtener los mensajes.")

# ENDPOINT PRINCIPAL MODIFICADO
@app.post("/chat-stream", tags=["Chat"])
async def chat_stream_handler(chat_request: ChatRequest, request: Request):
    country_code = request.headers.get('X-Country-Code', None)
    
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    
    return StreamingResponse(
        stream_chat_response_generator(chat_request, country_code),
        headers=headers
    )
