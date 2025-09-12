# src/main.py

import json
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings, log
from src.models.chat_models import ChatRequest
from src.modules import pse_client, gemini_client, rag_client
from src.core.prompts import PIDA_SYSTEM_PROMPT

app = FastAPI(
    title="PIDA Backend API - Logic Only",
    description="API para el asistente jurídico PIDA, optimizada para streaming con SSE."
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

# --- LÓGICA DE STREAMING RE-ARQUITECTADA (GENERADOR SSE) ---
async def stream_chat_response_generator(chat_request: ChatRequest, country_code: str | None):
    """
    Generador que orquesta la búsqueda de contexto de forma no bloqueante y
    realiza el streaming de la respuesta del AI, enviando actualizaciones de estado.
    """
    
    # Función auxiliar para crear eventos SSE
    def create_sse_event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    try:
        # 1. Notificar al cliente que el proceso ha comenzado
        yield create_sse_event({"event": "status", "message": "Iniciando búsqueda de fuentes..."})
        log.info(f"Iniciando búsqueda de fuentes (PSE y RAG) para prompt: '{chat_request.prompt[:50]}...'")

        # 2. Preparar las tareas de búsqueda
        search_tasks = [
            pse_client.search_for_sources(chat_request.prompt, num_results=3),
            rag_client.search_internal_documents(chat_request.prompt)
        ]
        
        # 3. Procesar tareas a medida que se completan (NO BLOQUEANTE)
        combined_context = ""
        # asyncio.as_completed devuelve las tareas en el orden en que terminan
        for task in asyncio.as_completed(search_tasks):
            try:
                result = await task
                combined_context += result
                log.info("Una fuente de contexto ha sido procesada exitosamente.")
                # Notificar al cliente sobre el progreso
                yield create_sse_event({"event": "status", "message": "Contexto encontrado. Procesando..."})
            except Exception as e:
                log.error(f"Una tarea de búsqueda falló: {e}", exc_info=True)
                # Opcional: notificar al cliente sobre el fallo de una fuente
                yield create_sse_event({"event": "status", "message": "Error al buscar en una de las fuentes."})
        
        # 4. Construir el prompt final y notificar al cliente
        log.info("Todas las búsquedas de contexto han finalizado.")
        yield create_sse_event({"event": "status", "message": "Generando análisis jurídico..."})

        final_prompt = f"Contexto geográfico: {country_code}\n{combined_context}\n\n---\n\nPregunta del usuario: {chat_request.prompt}"
        history_for_gemini = gemini_client.prepare_history_for_vertex(chat_request.history)

        log.info("Prompt final construido. Enviando a Gemini para iniciar streaming...")
        
        # 5. Iniciar el streaming de la respuesta de Gemini
        async for chunk in gemini_client.generate_streaming_response(
            system_prompt=PIDA_SYSTEM_PROMPT,
            prompt=final_prompt,
            history=history_for_gemini
        ):
            yield create_sse_event({'text': chunk})

        # 6. Finalizar el stream
        log.info("Streaming finalizado exitosamente. Enviando evento 'done'.")
        yield create_sse_event({'event': 'done'})

    except Exception as e:
        log.error(f"Error crítico durante el proceso de streaming: {e}", exc_info=True)
        error_message = json.dumps({"error": "Lo siento, ocurrió un error interno al generar la respuesta."})
        yield f"data: {error_message}\n\n"


# --- ENDPOINTS DE LA API ---

@app.get("/status", tags=["Status"])
def read_status():
    """Endpoint de verificación para confirmar que el servicio está activo."""
    return {"status": "ok", "message": "PIDA Backend de Lógica funcionando."}

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
