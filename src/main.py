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


# --- LÓGICA DE STREAMING (GENERADOR SSE) ---
async def stream_chat_response_generator(chat_request: ChatRequest, country_code: str | None):
    """
    Generador que orquesta la búsqueda de contexto y el streaming de la respuesta del AI.
    Produce eventos en formato Server-Sent Events (SSE).
    """
    try:
        log.info(f"Iniciando búsqueda de fuentes (PSE y RAG). País: {country_code or 'No especificado'}")
        
        search_tasks = [
            pse_client.search_for_sources(chat_request.prompt, num_results=3),
            rag_client.search_internal_documents(chat_request.prompt)
        ]
        results = await asyncio.gather(*search_tasks)
        pse_context, rag_context = results[0], results[1]

        combined_context = f"{pse_context}{rag_context}"
        final_prompt = f"Contexto geográfico: {country_code}\n{combined_context}\n\n---\n\nPregunta del usuario: {chat_request.prompt}"

        history_for_gemini = gemini_client.prepare_history_for_vertex(chat_request.history)

        log.info("Prompt final construido. Enviando a Gemini para iniciar streaming...")
        
        async for chunk in gemini_client.generate_streaming_response(
            system_prompt=PIDA_SYSTEM_PROMPT,
            prompt=final_prompt,
            history=history_for_gemini
        ):
            yield f"data: {json.dumps({'text': chunk})}\n\n"

        log.info("Streaming finalizado exitosamente. Enviando evento 'done'.")
        yield f"data: {json.dumps({'event': 'done'})}\n\n"

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
    
    # --- CORRECCIÓN CLAVE ---
    # Se añaden las cabeceras para desactivar el buffering del proxy.
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no" # ¡Esta es la línea más importante!
    }
    
    return StreamingResponse(
        stream_chat_response_generator(chat_request, country_code),
        headers=headers
    )
