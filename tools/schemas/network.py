"""
Esquemas de herramientas para el dominio: Network.
"""

from typing import Any, Dict, List

NETWORK_TOOLS: List[Dict[str, Any]] = [   {   'function': {   'description': 'Superpoder: Realiza una búsqueda web en tiempo real para encontrar '
                                       'documentación técnica de librerías, foros o ejemplos de código.',
                        'name': 'search_web',
                        'parameters': {   'properties': {   'max_results': {   'description': 'Cantidad de resultados '
                                                                                              'a retornar (por defecto '
                                                                                              '5).',
                                                                               'type': 'integer'},
                                                            'query': {   'description': 'Término o pregunta técnica a '
                                                                                        'buscar.',
                                                                         'type': 'string'}},
                                          'required': ['query'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Superpoder: Descarga y extrae el texto limpio y legible de una URL o '
                                       'documentación técnica en la web.',
                        'name': 'fetch_web_page',
                        'parameters': {   'properties': {   'max_chars': {   'description': 'Límite máximo de '
                                                                                            'caracteres a extraer (por '
                                                                                            'defecto 4000).',
                                                                             'type': 'integer'},
                                                            'url': {   'description': 'URL de la página web a leer.',
                                                                       'type': 'string'}},
                                          'required': ['url'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'MCP Client ÚNICAMENTE: Consulta herramientas externas en servidores MCP '
                                       'remotos. NUNCA uses esta herramienta para listar archivos, carpetas o código '
                                       "del proyecto local; para ver archivos del proyecto usa 'list_directory' o "
                                       "'get_repo_map'.",
                        'name': 'list_mcp_tools',
                        'parameters': {'properties': {}, 'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'MCP Client: Ejecuta una herramienta externa en un servidor MCP conectado vía '
                                       'JSON-RPC 2.0.',
                        'name': 'call_mcp_tool',
                        'parameters': {   'properties': {   'arguments': {   'description': 'Diccionario de argumentos '
                                                                                            'para la herramienta.',
                                                                             'type': 'object'},
                                                            'server_name': {   'description': 'Nombre del servidor MCP '
                                                                                              'registrado.',
                                                                               'type': 'string'},
                                                            'tool_name': {   'description': 'Nombre de la herramienta '
                                                                                            'en el servidor MCP.',
                                                                             'type': 'string'}},
                                          'required': ['server_name', 'tool_name'],
                                          'type': 'object'}},
        'type': 'function'}]
