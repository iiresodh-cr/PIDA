# src/main.py

import json
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings, log
from src.models.chat_models import ChatRequest
# Se añade el nuevo cliente para Firestore
from src.modules import pse_client, gemini_client, rag_client, firestore_client
from src.core.prompts import PIDA_SYSTEM_PROMPT

app = FastAPI(
    title="PIDA Backend API - con Persistencia en Firestore",
    description="API para el asistente jurídico PIDA, optimizada para streaming con SSE y guardado en base de datos."
)

# --- CONFIGURACIÓN DE CORS (AJUSTADA PARA SER MÁS PERMISIVA) ---
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
    allow_methods=["*"], # Permite todos los métodos
    allow_headers=["*"], # Permite todas las cabeceras
)

# --- LÓGICA DE STREAMING RE-ARQUITECTADA CON FIRESTORE ---
async def stream_chat_response_generator(chat_request: ChatRequest, country_code: str | None):
    """
    Generador que orquesta la búsqueda, el guardado en base de datos y
    el streaming de la respuesta del AI, enviando actualizaciones de estado.
    """
    
    # Función auxiliar para crear eventos SSE
    def create_sse_event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    try:
        # 1. OBTENER O CREAR CONVERSACIÓN EN FIRESTORE
        log.info(f"Buscando o creando conversación para el usuario: {chat_request.user_id}")
        conversation = await firestore_client.get_or_create_conversation(chat_request.user_id, chat_request.conversation_id)
        current_convo_id = conversation["id"]
        
        # Devuelve el ID de la conversación al cliente para que lo guarde
        yield create_sse_event({"event": "conversation_id", "id": current_convo_id})

        # 2. GUARDAR EL MENSAJE DEL USUARIO EN FIRESTORE
        await firestore_client.add_message_to_conversation(
            user_id=chat_request.user_id,
            conversation_id=current_convo_id,
            role="user",
            content=chat_request.prompt
        )
        
        # 3. ACTUALIZAR TÍTULO SI ES UN CHAT NUEVO
        if conversation.get('title') == 'Nuevo Chat':
            new_title = ' '.join(chat_request.prompt.split(' ')[0:5])
            if len(chat_request.prompt.split(' ')) > 5: new_title += '...'
            await firestore_client.update_conversation_title(chat_request.user_id, current_convo_id, new_title)

        # 4. Notificar al cliente que el proceso de búsqueda ha comenzado (Lógica original)
        yield create_sse_event({"event": "status", "message": "Iniciando búsqueda de fuentes..."})
        log.info(f"Iniciando búsqueda de fuentes (PSE y RAG) para prompt: '{chat_request.prompt[:50]}...'")

        # 5. Preparar las tareas de búsqueda (Lógica original)
        search_tasks = [
            pse_client.search_for_sources(chat_request.prompt, num_results=3),
            rag_client.search_internal_documents(chat_request.prompt)
        ]
        
        # 6. Procesar tareas a medida que se completan (Lógica original)
        combined_context = ""
        for task in asyncio.as_completed(search_tasks):
            try:
                result = await task
                combined_context += result
                log.info("Una fuente de contexto ha sido procesada exitosamente.")
                yield create_sse_event({"event": "status", "message": "Contexto encontrado. Procesando..."})
            except Exception as e:
                log.error(f"Una tarea de búsqueda falló: {e}", exc_info=True)
                yield create_sse_event({"event": "status", "message": "Error al buscar en una de las fuentes."})
        
        # 7. OBTENER HISTORIAL DESDE FIRESTORE PARA ENVIAR A GEMINI
        log.info("Todas las búsquedas de contexto han finalizado. Obteniendo historial de Firestore.")
        history_from_db = await firestore_client.get_conversation_history(chat_request.user_id, current_convo_id)
        # Se quita el último mensaje del usuario, ya que está en el prompt principal.
        history_for_gemini_pydantic = history_from_db[:-1]
        
        # 8. Construir el prompt final y notificar al cliente
        yield create_sse_event({"event": "status", "message": "Generando análisis jurídico..."})

        final_prompt = f"Contexto geográfico: {country_code}\n{combined_context}\n\n---\n\nPregunta del usuario: {chat_request.prompt}"
        history_for_vertex = gemini_client.prepare_history_for_vertex(history_for_gemini_pydantic)

        log.info("Prompt final construido. Enviando a Gemini para iniciar streaming...")
        
        # 9. Iniciar el streaming de la respuesta de Gemini
        full_response_text = ""
        async for chunk in gemini_client.generate_streaming_response(
            system_prompt=PIDA_SYSTEM_PROMPT,
            prompt=final_prompt,
            history=history_for_vertex
        ):
            full_response_text += chunk
            yield create_sse_event({'text': chunk})

        # 10. GUARDAR RESPUESTA COMPLETA DEL MODELO EN FIRESTORE
        await firestore_client.add_message_to_conversation(
            user_id=chat_request.user_id,
            conversation_id=current_convo_id,
            role="model",
            content=full_response_text
        )

        # 11. Finalizar el stream
        log.info("Streaming finalizado exitosamente. Respuesta guardada. Enviando evento 'done'.")
        yield create_sse_event({'event': 'done'})

    except Exception as e:
        log.error(f"Error crítico durante el proceso de streaming: {e}", exc_info=True)
        error_message = json.dumps({"error": "Lo siento, ocurrió un error interno al generar la respuesta."})
        yield f"data: {error_message}\n\n"


# --- ENDPOINTS DE LA API ---

@app.get("/status", tags=["Status"])
def read_status():
    """Endpoint de verificación para confirmar que el servicio está activo."""
    return {"status": "ok", "message": "PIDA Backend con Firestore funcionando."}

# ENDPOINT para obtener la lista de todas las conversaciones de un usuario
@app.get("/conversations/{user_id}", tags=["Conversations"])
async def get_conversations(user_id: str):
    """Obtiene la lista de todas las conversaciones para un usuario específico."""
    try:
        conversations = await firestore_client.get_user_conversations(user_id)
        return conversations
    except Exception as e:
        log.error(f"Error al obtener conversaciones para el usuario {user_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron obtener las conversaciones.")

# ENDPOINT para obtener los mensajes de un chat específico
@app.get("/conversations/{user_id}/{conversation_id}", tags=["Conversations"])
async def get_conversation_messages(user_id: str, conversation_id: str):
    """Obtiene todos los mensajes de una conversación específica."""
    try:
        messages = await firestore_client.get_conversation_history(user_id, conversation_id)
        return messages
    except Exception as e:
        log.error(f"Error al obtener mensajes para la conversación {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudieron obtener los mensajes.")

# ENDPOINT PRINCIPAL MODIFICADO para usar la nueva lógica
@app.post("/chat-stream", tags=["Chat"])
async def chat_stream_handler(chat_request: ChatRequest, request: Request):
    """
    Endpoint principal que maneja las solicitudes de chat y devuelve una respuesta en streaming.
    """
    country_code = request.headers.get('X-Country-Code', None)
    
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no" # ¡Crucial para evitar buffering de proxies!
    }
    
    return StreamingResponse(
        stream_chat_response_generator(chat_request, country_code),
        headers=headers
    )
