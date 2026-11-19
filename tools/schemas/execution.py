"""
Esquemas de herramientas para el dominio: Execution.
"""

from typing import Any, Dict, List

EXECUTION_TOOLS: List[Dict[str, Any]] = [   {   'function': {   'description': 'Ejecuta un comando en la consola (PowerShell en Windows) para correr tests, '
                                       'instalar dependencias o compilar.',
                        'name': 'run_command',
                        'parameters': {   'properties': {   'command': {   'description': 'Comando a ejecutar en la '
                                                                                          "terminal (ej. 'pytest', "
                                                                                          "'npm test').",
                                                                           'type': 'string'},
                                                            'cwd': {   'description': 'Directorio de trabajo opcional.',
                                                                       'type': 'string'}},
                                          'required': ['command'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Ejecuta las pruebas unitarias del proyecto de forma automatizada (por defecto '
                                       'con pytest).',
                        'name': 'run_tests',
                        'parameters': {   'properties': {   'test_target': {   'description': 'Ruta o archivo '
                                                                                              'específico de tests a '
                                                                                              'ejecutar (opcional).',
                                                                               'type': 'string'}},
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Inicia un comando persistente en segundo plano (servidor de desarrollo, '
                                       'watcher, script largo) y retorna un process_id.',
                        'name': 'start_background_process',
                        'parameters': {   'properties': {   'command': {   'description': 'Comando a ejecutar en '
                                                                                          'segundo plano.',
                                                                           'type': 'string'},
                                                            'cwd': {   'description': 'Directorio de trabajo opcional.',
                                                                       'type': 'string'}},
                                          'required': ['command'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Consulta el estado, salida estándar y errores de un proceso en segundo plano '
                                       'por su process_id.',
                        'name': 'get_process_status',
                        'parameters': {   'properties': {   'process_id': {   'description': 'ID del proceso retornado '
                                                                                             'por '
                                                                                             'start_background_process.',
                                                                              'type': 'string'}},
                                          'required': ['process_id'],
                                          'type': 'object'}},
        'type': 'function'},
    {   'function': {   'description': 'Termina y cancela de forma forzosa un proceso en segundo plano y todo su árbol '
                                       'de procesos.',
                        'name': 'cancel_process',
                        'parameters': {   'properties': {   'process_id': {   'description': 'ID del proceso a '
                                                                                             'cancelar.',
                                                                              'type': 'string'}},
                                          'required': ['process_id'],
                                          'type': 'object'}},
        'type': 'function'}]
