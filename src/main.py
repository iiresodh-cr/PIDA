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

# --- LÓGICA DE STREAMING CON PROCESO DE PENSAMIENTO ---
async def stream_chat_response_generator(chat_request: ChatRequest, country_code: str | None):
    """
    Generador que orquesta la búsqueda y emite eventos de estado
    detallados ("proceso de pensamiento") antes de hacer el streaming de la respuesta final.
    """
    
    def create_sse_event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    try:
        # 1. Inicia el proceso
        yield create_sse_event({"event": "status", "message": "Iniciando... 🕵️"})
        await asyncio.sleep(0.5) # Pausa para mejorar la experiencia de usuario

        # 2. Emite los pasos de la búsqueda
        log.info(f"Iniciando búsqueda de fuentes (PSE y RAG) para prompt: '{chat_request.prompt[:50]}...'")
        yield create_sse_event({"event": "status", "message": "Consultando jurisprudencia y fuentes externas..."})
        
        search_tasks = [
            pse_client.search_for_sources(chat_request.prompt, num_results=3),
            rag_client.search_internal_documents(chat_request.prompt)
        ]
        
        # 3. Procesa tareas y notifica sobre el progreso
        combined_context = ""
        task_count = len(search_tasks)
        for i, task in enumerate(asyncio.as_completed(search_tasks)):
            try:
                result = await task
                combined_context += result
                # Envía una actualización después de que cada tarea de búsqueda termina
                yield create_sse_event({"event": "status", "message": f"Fuente de contexto ({i+1}/{task_count}) procesada..."})
            except Exception as e:
                log.error(f"Una tarea de búsqueda falló: {e}", exc_info=True)
        
        await asyncio.sleep(0.5)
        yield create_sse_event({"event": "status", "message": "Contexto recopilado. Construyendo la consulta para el análisis..."})
        await asyncio.sleep(0.5)

        # 4. Construye el prompt final y notifica antes de llamar a Gemini
        final_prompt = f"Contexto geográfico: {country_code}\n{combined_context}\n\n---\n\nPregunta del usuario: {chat_request.prompt}"
        history_for_gemini = gemini_client.prepare_history_for_vertex(chat_request.history)

        yield create_sse_event({"event": "status", "message": f"Enviando a {settings.GEMINI_MODEL} para generar la respuesta... 🧠"})
        log.info("Prompt final construido. Enviando a Gemini para iniciar streaming...")
        
        # 5. Inicia el streaming de la respuesta de Gemini
        async for chunk in gemini_client.generate_streaming_response(
            system_prompt=PIDA_SYSTEM_PROMPT,
            prompt=final_prompt,
            history=history_for_gemini
        ):
            yield create_sse_event({'text': chunk})

        # 6. Finaliza el stream
        log.info("Streaming finalizado exitosamente. Enviando evento 'done'.")
        yield create_sse_event({'event': 'done'})

    except Exception as e:
        log.error(f"Error crítico durante el proceso de streaming: {e}", exc_info=True)
        error_message = json.dumps({"error": "Lo siento, ocurrió un error interno al generar la respuesta."})
        yield f"data: {error_message}\n\n"


# --- ENDPOINTS DE LA API (sin cambios) ---
@app.get("/status", tags=["Status"])
def read_status():
    return {"status": "ok", "message": "PIDA Backend de Lógica funcionando."}

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
