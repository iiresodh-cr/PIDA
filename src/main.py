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
# Se especifican los dominios desde los cuales se permitirán las solicitudes.
origins = [
    "https://pida.iiresodh.org",
    "https://pida-ai.com",
    # También es buena práctica añadir dominios de prueba si los tienes
    "http://localhost",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST", "GET"], # Se especifican los métodos permitidos
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
        
        # Ejecuta las búsquedas de contexto en paralelo para mayor eficiencia
        search_tasks = [
            pse_client.search_for_sources(chat_request.prompt, num_results=3),
            rag_client.search_internal_documents(chat_request.prompt)
        ]
        results = await asyncio.gather(*search_tasks)
        pse_context, rag_context = results[0], results[1]

        # Combina los contextos para enriquecer el prompt final
        combined_context = f"{pse_context}{rag_context}"
        final_prompt = f"Contexto geográfico: {country_code}\n{combined_context}\n\n---\n\nPregunta del usuario: {chat_request.prompt}"

        history_for_gemini = gemini_client.prepare_history_for_vertex(chat_request.history)

        log.info("Prompt final construido. Enviando a Gemini para iniciar streaming...")
        
        # Llama al generador de Gemini y transmite cada trozo de texto al cliente
        async for chunk in gemini_client.generate_streaming_response(
            system_prompt=PIDA_SYSTEM_PROMPT,
            prompt=final_prompt,
            history=history_for_gemini
        ):
            # El formato SSE requiere la línea "data: " seguida de un salto de línea doble.
            # Enviamos un objeto JSON para mantener la estructura y flexibilidad.
            yield f"data: {json.dumps({'text': chunk})}\n\n"

        # Envía un evento final para notificar al cliente que la transmisión ha terminado.
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
    Endpoint principal que maneja las solicitudes de chat.
    Recibe el prompt del usuario y el historial, y devuelve una respuesta
    en streaming a través de Server-Sent Events (SSE).
    """
    # Extrae el código de país de las cabeceras si está disponible
    country_code = request.headers.get('X-Country-Code', None)
    
    return StreamingResponse(
        stream_chat_response_generator(chat_request, country_code),
        media_type="text/event-stream"
    )
    with open(STATIC_PATH / "index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
