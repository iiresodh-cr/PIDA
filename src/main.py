# src/main.py

import json
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from src.config import settings, log
from src.models.chat_models import ChatRequest
from src.modules import pse_client, gemini_client, rag_client
from src.core.prompts import PIDA_SYSTEM_PROMPT

# --- NUEVO: Configuración para servir archivos estáticos ---
BASE_DIR = Path(__file__).resolve().parent
STATIC_PATH = BASE_DIR / "static"

app = FastAPI(title="PIDA Backend API - Integrated")

# --- LÓGICA DE STREAMING (SSE) ---
async def stream_chat_response_generator(chat_request: ChatRequest, country_code: str | None):
    """
    Generador principal que orquesta la búsqueda y el streaming de la respuesta del AI.
    """
    try:
        log.info(f"Iniciando búsqueda de fuentes (PSE y RAG) para el prompt. País: {country_code}")
        search_tasks = [
            pse_client.search_for_sources(chat_request.prompt, num_results=3),
            rag_client.search_internal_documents(chat_request.prompt)
        ]
        results = await asyncio.gather(*search_tasks)
        pse_context, rag_context = results[0], results[1]

        combined_context = f"{pse_context}{rag_context}"
        final_prompt = f"Contexto geográfico: {country_code}\n{combined_context}\n\n---\n\nPregunta del usuario: {chat_request.prompt}"

        history_for_gemini = gemini_client.prepare_history_for_vertex(chat_request.history)

        log.info("Enviando prompt final a Gemini y comenzando streaming...")
        
        # Llama al generador de Gemini y transmite cada trozo
        async for chunk in gemini_client.generate_streaming_response(
            system_prompt=PIDA_SYSTEM_PROMPT,
            prompt=final_prompt,
            history=history_for_gemini
        ):
            # El formato SSE es "data: <contenido>\n\n"
            # Enviamos un objeto JSON para estructurar los datos
            yield f"data: {json.dumps({'text': chunk})}\n\n"

        # Envía un evento final para que el cliente sepa que hemos terminado
        log.info("Streaming finalizado. Enviando evento 'done'.")
        yield f"data: {json.dumps({'event': 'done'})}\n\n"

    except Exception as e:
        log.error(f"Error crítico durante el streaming: {e}", exc_info=True)
        error_message = json.dumps({"error": "Lo siento, ocurrió un error en el servidor al generar la respuesta."})
        yield f"data: {error_message}\n\n"

# --- ENDPOINTS DE LA API ---

@app.post("/chat-stream", tags=["Chat"])
async def chat_stream_handler(chat_request: ChatRequest, request: Request):
    """
    Endpoint principal para manejar el chat con respuesta en streaming usando SSE.
    """
    country_code = request.headers.get('X-Country-Code', None)
    return StreamingResponse(
        stream_chat_response_generator(chat_request, country_code),
        media_type="text/event-stream"
    )

@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def serve_chat_ui():
    """
    Sirve el archivo HTML principal que contiene la interfaz del chat.
    """
    with open(STATIC_PATH / "index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
