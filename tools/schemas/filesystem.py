"""
Esquemas de herramientas para el dominio: Filesystem.
"""

from typing import Any, Dict, List

FILESYSTEM_TOOLS: List[Dict[str, Any]] = [   {   'function': {   'description': 'Lee un rango de líneas de un archivo de código con números de línea para no '
                                       'desbordar el contexto.',
                        'name': 'read_file',
                        'parameters': {   'properties': {   'end_line': {   'description': 'Línea final a leer (por '
                                                                                           'defecto 200).',
                                                                            'type': 'integer'},
                                                            'path': {   'description': 'Ruta relativa o absoluta del '
                                                                                       'archivo a leer.',
                                                                        'type': 'string'},
                                                            'start_line': {   'description': 'Línea inicial a leer '
                                                                                             '(por defecto 1).',
                                                                              'type': 'integer'}},
                                          'required': ['path'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Reemplaza exactamente una sección de texto existente (target) por nuevo código '
                                       '(replacement). Requiere indentación exacta.',
                        'name': 'edit_file',
                        'parameters': {   'properties': {   'path': {   'description': 'Ruta del archivo a editar.',
                                                                        'type': 'string'},
                                                            'replacement': {   'description': 'Nuevo texto que '
                                                                                              "sustituirá a 'target'.",
                                                                               'type': 'string'},
                                                            'target': {   'description': 'Texto exacto que se desea '
                                                                                         'reemplazar, incluyendo '
                                                                                         'espacios y sangrías.',
                                                                          'type': 'string'}},
                                          'required': ['path', 'target', 'replacement'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Crea un archivo nuevo o reemplaza por completo el contenido de uno existente.',
                        'name': 'write_file',
                        'parameters': {   'properties': {   'content': {   'description': 'Contenido completo del '
                                                                                          'archivo.',
                                                                           'type': 'string'},
                                                            'path': {   'description': 'Ruta del archivo a crear o '
                                                                                       'sobrescribir.',
                                                                        'type': 'string'}},
                                          'required': ['path', 'content'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Elimina de forma segura un archivo existente en el disco.',
                        'name': 'delete_file',
                        'parameters': {   'properties': {   'path': {   'description': 'Ruta del archivo a eliminar.',
                                                                        'type': 'string'}},
                                          'required': ['path'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Mueve o renombra un archivo existente a una nueva ruta.',
                        'name': 'move_file',
                        'parameters': {   'properties': {   'destination': {   'description': 'Nueva ruta o nombre de '
                                                                                              'destino.',
                                                                               'type': 'string'},
                                                            'source': {   'description': 'Ruta del archivo original.',
                                                                          'type': 'string'}},
                                          'required': ['source', 'destination'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Aplica una edición atómica y transaccional verificando SHA256 o similitud '
                                       'fuzzy, generando diff unificado.',
                        'name': 'apply_patch',
                        'parameters': {   'properties': {   'expected_sha256': {   'description': 'Hash SHA-256 '
                                                                                                  'opcional para '
                                                                                                  'prevenir colisiones '
                                                                                                  'o ediciones '
                                                                                                  'concurrentes.',
                                                                                   'type': 'string'},
                                                            'path': {   'description': 'Ruta del archivo a modificar.',
                                                                        'type': 'string'},
                                                            'replacement': {   'description': 'Nuevo texto o bloque de '
                                                                                              'código que reemplazará '
                                                                                              'al objetivo.',
                                                                               'type': 'string'},
                                                            'target': {   'description': 'Texto exacto o bloque de '
                                                                                         'código que se va a '
                                                                                         'sustituir.',
                                                                          'type': 'string'}},
                                          'required': ['path', 'target', 'replacement'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Lista los archivos y carpetas del proyecto local o de un directorio específico '
                                       "(por ejemplo '.' para la raíz). Úsala obligatoriamente cuando el usuario "
                                       'pregunte qué archivos hay en la raíz o en una carpeta.',
                        'name': 'list_directory',
                        'parameters': {   'properties': {   'max_depth': {   'description': 'Profundidad máxima de '
                                                                                            'recursión (por defecto '
                                                                                            '2).',
                                                                             'type': 'integer'},
                                                            'path': {   'description': 'Directorio a explorar (por '
                                                                                       "defecto '.').",
                                                                        'type': 'string'}},
                                          'type': 'object'}},
        'type': 'function'}]
