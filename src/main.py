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

# --- LÓGICA DE STREAMING MEJORADA (GENERADOR SSE) ---
async def stream_chat_response_generator(chat_request: ChatRequest, country_code: str | None):
    """
    Generador mejorado que envía actualizaciones de estado al cliente
    mientras busca contexto, y luego transmite la respuesta del AI.
    """
    try:
        # --- FUNCIÓN AUXILIAR PARA ENVIAR EVENTOS SSE ---
        def create_sse_event(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        # 1. Notificar al cliente que la búsqueda ha comenzado
        yield create_sse_event({"event": "status", "message": "Buscando en documentos y fuentes externas..."})
        log.info(f"Iniciando búsqueda de fuentes (PSE y RAG). País: {country_code or 'No especificado'}")

        # 2. Realizar las búsquedas de contexto en paralelo
        search_tasks = [
            pse_client.search_for_sources(chat_request.prompt, num_results=3),
            rag_client.search_internal_documents(chat_request.prompt)
        ]
        results = await asyncio.gather(*search_tasks)
        pse_context, rag_context = results[0], results[1]

        # 3. Notificar al cliente que se está generando la respuesta
        yield create_sse_event({"event": "status", "message": "Generando análisis jurídico..."})
        log.info("Contexto recolectado. Construyendo prompt final para Gemini...")

        combined_context = f"{pse_context}{rag_context}"
        final_prompt = f"Contexto geográfico: {country_code}\n{combined_context}\n\n---\n\nPregunta del usuario: {chat_request.prompt}"

        history_for_gemini = gemini_client.prepare_history_for_vertex(chat_request.history)

        log.info("Enviando a Gemini para iniciar streaming...")

        # 4. Iniciar el streaming de la respuesta de Gemini
        async for chunk in gemini_client.generate_streaming_response(
            system_prompt=PIDA_SYSTEM_PROMPT,
            prompt=final_prompt,
            history=history_for_gemini
        ):
            yield create_sse_event({'text': chunk})

        # 5. Enviar el evento de finalización
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
        "X-Accel-Buffering": "no" # ¡Muy importante para evitar buffering de proxy!
    }
    
    return StreamingResponse(
        stream_chat_response_generator(chat_request, country_code),
        headers=headers
    )
