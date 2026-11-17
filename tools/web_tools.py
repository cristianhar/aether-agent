"""
Superpoder: Herramientas de navegación e investigación web en vivo.
Permite consultar documentación técnica de librerías, foros y APIs actualizadas sin claves de pago.
"""

import html
import os
import re
import urllib.parse
import urllib.request
from typing import List, Dict


def is_offline_mode() -> bool:
    """Verifica si el entorno está configurado para operación estricta 100% offline."""
    return os.environ.get("AETHER_OFFLINE", "0") in ("1", "true", "True")


def search_web(query: str, max_results: int = 5) -> str:
    """
    Superpoder: Realiza una búsqueda web en tiempo real para encontrar documentación de librerías,
    soluciones a errores de compilación o ejemplos técnicos de código.
    Respeta el perfil 100% offline si AETHER_OFFLINE=1.
    """
    if is_offline_mode():
        return "🌐 Modo 100% Offline activo: Búsqueda web externa deshabilitada por configuración de privacidad."

    clean_query = query.strip()
    if not clean_query:
        return "Error: La consulta de búsqueda no puede estar vacía."

    encoded_query = urllib.parse.quote_plus(clean_query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            html_content = response.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"Aviso de red: No se pudo conectar a la búsqueda web ({e}). Puedes continuar sin conexión."

    # Extraer resultados usando regex para evitar dependencias externas pesadas
    results: List[Dict[str, str]] = []
    
    # Bloques de resultados en DuckDuckGo HTML
    result_blocks = re.findall(
        r'<a class="result__snippet[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html_content,
        re.DOTALL
    )

    if not result_blocks:
        # Fallback para estructura alternativa de resultados
        titles_and_urls = re.findall(
            r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html_content,
            re.DOTALL
        )
        snippets = re.findall(
            r'<a class="result__snippet[^>]*>(.*?)</a>',
            html_content,
            re.DOTALL
        )
        for i in range(min(len(titles_and_urls), len(snippets), max_results)):
            raw_url = titles_and_urls[i][0]
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            snippet = html.unescape(snippet)
            results.append({"url": raw_url, "snippet": snippet})
    else:
        for raw_url, raw_snippet in result_blocks[:max_results]:
            snippet = re.sub(r"<[^>]+>", "", raw_snippet).strip()
            snippet = html.unescape(snippet)
            # Decodificar redirect de duckduckgo si aplica
            match_ud = re.search(r"uddg=([^&]+)", raw_url)
            final_url = urllib.parse.unquote(match_ud.group(1)) if match_ud else raw_url
            results.append({"url": final_url, "snippet": snippet})

    if not results:
        return f"No se obtuvieron fragmentos directos para la búsqueda: '{query}'."

    output = [f"Resultados de búsqueda web para: '{query}':\n"]
    for idx, r in enumerate(results, 1):
        output.append(f"{idx}. URL: {r['url']}")
        output.append(f"   Resumen: {r['snippet']}\n")

    return "\n".join(output)


def fetch_web_page(url: str, max_chars: int = 4000) -> str:
    """
    Superpoder: Descarga y extrae el texto legible de una página web o documentación técnica.
    Elimina scripts, etiquetas HTML y estilos para ahorrar tokens de contexto.
    Respeta el perfil 100% offline si AETHER_OFFLINE=1.
    """
    if is_offline_mode():
        return "🌐 Modo 100% Offline activo: Lectura de URLs externas deshabilitada por configuración de privacidad."

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "")
            raw_data = response.read()
            html_text = raw_data.decode("utf-8", errors="replace")
    except Exception as e:
        return f"Error al descargar la página '{url}': {e}"

    # Limpiar scripts, estilos y etiquetas HTML
    text = re.sub(r"<script[\s\S]*?</script>", "", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    # Normalizar espacios
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return f"Aviso: La página '{url}' no devolvió contenido de texto legible."

    truncated = text[:max_chars]
    res = f"--- Contenido extraído de {url} ({len(text)} caracteres) ---\n\n{truncated}"
    if len(text) > max_chars:
        res += f"\n\n... [Contenido truncado a {max_chars} caracteres para no desbordar el contexto]"
    return res
