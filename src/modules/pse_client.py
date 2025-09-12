# src/modules/pse_client.py

import httpx
import io
from bs4 import BeautifulSoup
from pypdf import PdfReader
from src.config import settings, log

FETCH_ERROR_MESSAGE = "No se pudo extraer contenido de esta fuente."
MAX_PDF_PAGES_TO_READ = 10 # <-- NUEVA CONSTANTE DE OPTIMIZACIÓN

async def _fetch_and_parse_url(url: str, client: httpx.AsyncClient) -> str:
    """
    Función auxiliar para descargar y extraer el texto de una URL,
    optimizada para leer solo las primeras páginas de un PDF.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        # Aumentamos el timeout general por si la descarga inicial es lenta
        response = await client.get(url, headers=headers, timeout=20.0, follow_redirects=True)
        response.raise_for_status()
        
        content_type = response.headers.get("content-type", "").lower()

        # Opción 1: El contenido es un PDF (LÓGICA OPTIMIZADA)
        if "application/pdf" in content_type:
            log.info(f"Detectado PDF en la URL: {url}. Extrayendo texto de las primeras {MAX_PDF_PAGES_TO_READ} páginas...")
            pdf_bytes = io.BytesIO(response.content)
            reader = PdfReader(pdf_bytes)
            
            text_content = ""
            # Leemos solo hasta un máximo de páginas para evitar la lentitud
            for i, page in enumerate(reader.pages):
                if i >= MAX_PDF_PAGES_TO_READ:
                    log.info(f"Límite de {MAX_PDF_PAGES_TO_READ} páginas alcanzado para {url}. Deteniendo lectura.")
                    break
                if page.extract_text():
                    text_content += page.extract_text()

            return text_content.replace("\\n", " ").replace("\n", " ").strip()[:7000]

        # Opción 2: El contenido es HTML
        elif "text/html" in content_type:
            log.info(f"Detectado HTML en la URL: {url}. Extrayendo texto...")
            soup = BeautifulSoup(response.text, 'lxml')
            paragraphs = [p.get_text() for p in soup.find_all('p')]
            content = " ".join(paragraphs).replace("\\n", " ").replace("\n", " ").strip()
            return content[:7000] if content else FETCH_ERROR_MESSAGE

        # Opción 3: Contenido no soportado
        else:
            log.warning(f"Contenido no soportado en la URL {url} (Content-Type: {content_type})")
            return FETCH_ERROR_MESSAGE

    except Exception as e:
        log.warning(f"No se pudo obtener el contenido de la URL {url}: {e}")
        return FETCH_ERROR_MESSAGE

async def search_for_sources(query: str, num_results: int = 3) -> str:
    """
    Realiza una búsqueda en el PSE y extrae el contenido de las páginas.
    """
    search_url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": settings.PSE_API_KEY, "cx": settings.PSE_ID, "q": query, "num": num_results}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            results = response.json()

            if "items" not in results or not results["items"]:
                return "No se encontraron resultados de búsqueda externos."

            formatted_results = "\\n\\n### Contexto de Búsqueda Externa:\\n"
            for item in results["items"]:
                title = item.get("title", "Sin Título")
                link = item.get("link", "#")
                snippet = item.get("snippet", "No hay descripción.").replace("\n", " ")
                
                page_content = await _fetch_and_parse_url(link, client)
                
                final_content = page_content if page_content != FETCH_ERROR_MESSAGE else snippet
                
                formatted_results += f"Título: **[{title}]({link})**\\n"
                formatted_results += f"Contenido de la Página: {final_content}\\n\\n"
            
            return formatted_results

        except Exception as e:
            log.error(f"Error inesperado en el cliente de PSE: {e}")
            return "Hubo un error al realizar la búsqueda externa."
