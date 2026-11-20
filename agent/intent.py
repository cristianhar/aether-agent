"""
agent/intent.py - Clasificador semántico de intención para AETHER IDE.

Enruta las solicitudes del usuario de forma modular y extensible sin listas rígidas
o hardcodeadas en el orquestador:
- CONVERSATIONAL: Saludos, despedidas, cortesía o interacción social.
- QUESTION: Consultas explicativas o conceptuales que no mutan código.
- CODE_TASK: Creación, edición, ejecución, pruebas o inspección activa del repositorio.
"""

from enum import Enum
import re
from typing import Optional


class IntentType(str, Enum):
    CONVERSATIONAL = "conversational"
    QUESTION = "question"
    CODE_TASK = "code_task"


# Patrones que indican inequívocamente una tarea sobre el código o repositorio
_CODE_TASK_PATTERNS = [
    # Verbos de acción sobre archivos y sistema (ES y EN)
    r"\b(crea|crear|edita|editar|modifica|modificar|escribe|escribir|borra|elimina|eliminar)\b",
    r"\b(refactoriza|refactorizar|implementa|implementar|arregla|arreglar|corrige|corregir)\b",
    r"\b(resuelve|resolver|agrega|agregar|añade|añadir|testea|testear|prueba|probar)\b",
    r"\b(corre|correr|ejecuta|ejecutar|compila|compilar|instala|instalar|despliega)\b",
    r"\b(write|edit|modify|create|fix|solve|run|execute|test|delete|remove|refactor|build)\b",
    # Extensiones de archivo conocidas
    r"(\.(py|ts|tsx|js|jsx|json|md|html|css|yaml|yml|sh|bat|toml|sql|rs|go|c|cpp|h))\b",
    # Menciones a archivos o carpetas
    r"(@[a-zA-Z0-9_./\\-]+)",
    r"(/api/|src/|tests?/|desktop/|agent/|tools/|\.aether/)",
    # Bloques de código o diffs
    r"(```[\s\S]*?```)",
    r"\b(git|commit|push|pull|branch|merge|diff|status|checkpoint|undo)\b",
]

# Patrones que indican preguntas o consultas conceptuales/explicativas
_QUESTION_PATTERNS = [
    r"^(qué|que|cómo|como|cuál|cual|por qué|porque|dónde|donde|cuándo|cuando|explica|explícame|dime|puedes explicar)\b",
    r"^(what|how|why|where|when|explain|tell me|can you explain)\b",
    r"\?$",
]

# Patrones semánticos conversacionales (saludos, despedidas, agradecimientos)
_CONVERSATIONAL_PATTERNS = [
    r"^[¡¿]?\s*(hola|buenas|buen[oa]s?\s+(días|dias|tardes|noches)|saludos|qué\s+tal|que\s+tal|cómo\s+estás|como\s+estas|cómo\s+te\s+va|como\s+te\s+va|ey|hey)\b",
    r"^[¡¿]?\s*(hi|hello|hey|good\s+(morning|afternoon|evening)|howdy|greetings|what'?s\s+up|how\s+are\s+you)\b",
    r"^[¡¿]?\s*(gracias|muchas\s+gracias|vale|ok|okay|entendido|de\s+acuerdo|perfecto|genial|excelente|listo|chao|adiós|adios|hasta\s+luego)\b",
    r"^[¡¿]?\s*(thanks|thank\s+you|got\s+it|cool|awesome|great|bye|goodbye|see\s+you)\b",
]


def classify_intent(prompt: str) -> IntentType:
    """
    Clasifica la intención del usuario de forma jerárquica y analítica:
    1. Si contiene indicadores de código, rutas o verbos de mutación -> CODE_TASK.
    2. Si contiene patrones conversacionales cortos sin código -> CONVERSATIONAL.
    3. Si contiene patrones de pregunta conceptual -> QUESTION.
    4. Heurística de longitud: Si es un texto muy breve sin código -> CONVERSATIONAL.
       Si es extenso o estructurado -> CODE_TASK (para preservar proactividad).
    """
    cleaned = prompt.strip()
    if not cleaned:
        return IntentType.CONVERSATIONAL

    # 1. Comprobar indicadores de código o mutación de repositorio
    for pattern in _CODE_TASK_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            return IntentType.CODE_TASK

    # 2. Comprobar patrones conversacionales
    for pattern in _CONVERSATIONAL_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            return IntentType.CONVERSATIONAL

    # 3. Comprobar preguntas conceptuales
    for pattern in _QUESTION_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            return IntentType.QUESTION

    # 4. Heurística para frases breves (< 25 caracteres) de interacción humana común
    if len(cleaned) < 25 and not any(ch in cleaned for ch in "{}[]()<>=/\\;"):
        return IntentType.CONVERSATIONAL

    return IntentType.CODE_TASK
