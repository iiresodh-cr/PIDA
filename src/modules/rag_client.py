# src/modules/rag_client.py

import httpx
from src.config import log

RAG_API_URL = "https://pida-rag-api-640849120264.us-central1.run.app/query"

async def search_internal_documents(query: str) -> str:
    """
    Realiza una consulta al servicio RAG interno para buscar en los documentos indexados.
    """
    log.info(f"Consultando RAG interno con la query: '{query[:50]}...'")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                RAG_API_URL,
                json={"query": query},
                timeout=25.0
            )
            response.raise_for_status()
            data = response.json()

            if not data or "results" not in data or not data["results"]:
                log.info("RAG interno no devolvió resultados.")
                return ""

            formatted_results = "\n\n### Contexto de Documentos Internos (RAG):\n"
            for doc in data["results"]:
                source = doc.get("source", "Documento Interno")
                content = doc.get("content", "").replace("\n", " ").strip()
                formatted_results += f"**Fuente Interna:** {source}\n"
                formatted_results += f"**Contenido:** {content}\n\n"
            
            return formatted_results

        except httpx.RequestError as e:
            log.error(f"Error de red al contactar el servicio RAG interno en {RAG_API_URL}: {e}")
            return "\n\n### Contexto de Documentos Internos (RAG):\nError de conexión al buscar en los documentos internos.\n"
        except Exception as e:
            log.error(f"Error inesperado al procesar la respuesta del RAG interno: {e}")
            return "\n\n### Contexto de Documentos Internos (RAG):\nError al procesar la búsqueda en los documentos internos.\n"
