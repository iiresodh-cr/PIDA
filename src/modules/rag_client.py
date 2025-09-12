# src/modules/rag_client.py

import httpx
from src.config import log

# La URL de tu servicio de indexación. ¡Asegúrate que termine en /query!
RAG_API_URL = "https://pida-rag-api-640849120264.us-central1.run.app/query"

async def search_internal_documents(query: str) -> str:
    """
    Realiza una consulta al servicio RAG interno para buscar en los documentos indexados.
    Ahora es más resiliente a los timeouts y errores de red.
    """
    log.info(f"Consultando RAG interno con la query: '{query[:50]}...'")
    
    # Aumentamos ligeramente el timeout para dar margen a arranques en frío.
    timeout_config = httpx.Timeout(30.0, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout_config) as client:
        try:
            response = await client.post(
                RAG_API_URL,
                json={"query": query}
            )
            response.raise_for_status() # Lanza un error si la respuesta no es 2xx
            data = response.json()

            if not data or "results" not in data or not data["results"]:
                log.warning("RAG interno no devolvió resultados para la consulta.")
                return "" # Devolvemos una cadena vacía para no añadir texto innecesario al prompt

            # Formateamos los resultados para inyectarlos en el prompt
            formatted_results = "\n\n### Contexto de Documentos Internos (RAG):\n"
            for doc in data.get("results", []):
                title = doc.get("title")
                author = doc.get("author")
                source_filename = doc.get("source")
                content = doc.get("content", "").replace("\n", " ").strip()

                # Decidir qué título mostrar, dando prioridad al de la metadata
                display_title = title or source_filename or "Documento Interno"

                # Construir la cita EXACTAMENTE como lo pide prompts.py
                # Formato: Fuente: <Título>, Autor
                citation_line = f"**Fuente:** **<{display_title}>**"
                if author and author.strip() and author != "Autor Desconocido":
                    citation_line += f", {author}"

                # Ensamblar la salida final, asegurando que "Texto:" esté en una nueva línea
                formatted_results += f"{citation_line}\n"
                formatted_results += f"**Texto:**\n> {content}\n\n"
            
            
            return formatted_results

        except httpx.TimeoutException as e:
            # --- MANEJO DE ERROR MEJORADO ---
            log.error(f"Timeout al contactar el servicio RAG interno en {RAG_API_URL}: {e}", exc_info=True)
            return "\n\n### Contexto de Documentos Internos (RAG):\nEl servicio de búsqueda de documentos internos tardó demasiado en responder y no está disponible en este momento.\n"
        except httpx.RequestError as e:
            log.error(f"Error de red al contactar el servicio RAG interno en {RAG_API_URL}: {e}", exc_info=True)
            return "\n\n### Contexto de Documentos Internos (RAG):\nError de conexión al buscar en los documentos internos.\n"
        except Exception as e:
            log.error(f"Error inesperado al procesar la respuesta del RAG interno: {e}", exc_info=True)
            return "\n\n### Contexto de Documentos Internos (RAG):\nError al procesar la búsqueda en los documentos internos.\n"
