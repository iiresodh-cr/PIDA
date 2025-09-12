# src/modules/gemini_client.py

import vertexai
from vertexai.generative_models import GenerativeModel, Content, Part, GenerationConfig
from typing import List
from src.config import settings, log
from src.models.chat_models import ChatMessage

# --- INICIALIZACIÓN DEL CLIENTE Y MODELO ---
try:
    vertexai.init(project=settings.GOOGLE_CLOUD_PROJECT, location=settings.GOOGLE_CLOUD_LOCATION)

    # Configuración de generación
    generation_config = GenerationConfig(
        max_output_tokens=settings.MAX_OUTPUT_TOKENS,
        temperature=settings.TEMPERATURE,
        top_p=settings.TOP_P,
    )

    # Carga del modelo
    model = GenerativeModel(settings.GEMINI_MODEL)
    log.info(f"Cliente de Vertex AI inicializado y modelo '{settings.GEMINI_MODEL}' cargado.")

except Exception as e:
    log.critical(f"No se pudo inicializar Vertex AI o cargar el modelo: {e}", exc_info=True)
    model = None

# --- FUNCIONES AUXILIARES ---

def prepare_history_for_vertex(history: List[ChatMessage]) -> List[Content]:
    """Convierte nuestro historial de Pydantic al formato que espera la API de Gemini."""
    vertex_history = []
    for message in history:
        role = 'user' if message.role == 'user' else 'model'
        vertex_history.append(Content(role=role, parts=[Part.from_text(message.content)]))
    return vertex_history

async def generate_streaming_response(system_prompt: str, prompt: str, history: List[Content]):
    """
    Genera una respuesta del modelo Gemini en modo streaming.
    Retorna un generador asíncrono que produce trozos (chunks) de texto.
    """
    if not model:
        log.error("El modelo Gemini no está disponible.")
        yield "Error: El modelo de IA no está configurado correctamente."
        return

    try:
        # Crea la sesión de chat con el historial y el system prompt
        chat = model.start_chat(history=history)
        
        # El system prompt se concatena al inicio del primer prompt del usuario
        full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"
        
        # Envía el prompt y obtiene un stream de respuestas
        response_stream = chat.send_message(full_prompt, stream=True, generation_config=generation_config)

        # Itera sobre el stream y produce cada trozo de texto
        async for chunk in response_stream:
            if chunk.text:
                yield chunk.text

    except Exception as e:
        log.error(f"Error al generar la respuesta en streaming desde Gemini: {e}", exc_info=True)
        yield "Hubo un problema al contactar al servicio de IA."
