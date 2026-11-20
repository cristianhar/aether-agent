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


# Patrones que indican inequívocamente una tarea de modificación sobre el código o repositorio
_CODE_MUTATION_PATTERNS = [
    r"\b(crea|crear|edita|editar|modifica|modificar|escribe|escribir|borra|elimina|eliminar)\b",
    r"\b(refactoriza|refactorizar|implementa|implementar|arregla|arreglar|corrige|corregir)\b",
    r"\b(resuelve|resolver|agrega|agregar|añade|añadir|testea|testear|prueba|probar)\b",
    r"\b(corre|correr|ejecuta|ejecutar|compila|compilar|instala|instalar|despliega)\b",
    r"\b(write|edit|modify|create|fix|solve|run|execute|test|delete|remove|refactor|build)\b",
    r"\b(git\s+(commit|push|pull|merge|checkout|rebase))\b",
]

# Patrones que indican consultas explicativas o de comprensión de código existente
_EXPLANATORY_PATTERNS = [
    r"\b(qué\s+hace|que\s+hace|cómo\s+funciona|como\s+funciona|para\s+qué\s+sirve|para\s+que\s+sirve)\b",
    r"\b(explica|explícame|explicame|describe|describir|analiza|analizar)\b",
    r"\b(puedes\s+decirme|puedes\s+explicarme|me\s+puedes\s+decir|me\s+puedes\s+explicar|peudes\s+decirme)\b",
    r"\b(what\s+does|how\s+does|can\s+you\s+explain|tell\s+me\s+about|what\s+is\s+the\s+purpose)\b",
]

# Patrones generales de código (menciones, rutas, diffs)
_CODE_ENTITY_PATTERNS = [
    r"(\.(py|ts|tsx|js|jsx|json|md|html|css|yaml|yml|sh|bat|toml|sql|rs|go|c|cpp|h))\b",
    r"(@[a-zA-Z0-9_./\\-]+)",
    r"(/api/|src/|tests?/|desktop/|agent/|tools/|\.aether/)",
    r"(```[\s\S]*?```)",
    r"\b(git|status|diff|checkpoint|undo)\b",
]

# Patrones que indican preguntas o consultas conceptuales generales
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
    1. Si solicita explicación o consulta sobre código existente sin mutación -> QUESTION.
    2. Si contiene verbos de mutación o acciones activas -> CODE_TASK.
    3. Si contiene patrones conversacionales cortos -> CONVERSATIONAL.
    4. Si contiene entidades de código (sin ser explicativo puro) -> CODE_TASK.
    5. Heurística para frases breves sin código -> CONVERSATIONAL.
    """
    cleaned = prompt.strip()
    if not cleaned:
        return IntentType.CONVERSATIONAL

    has_mutation = any(re.search(p, cleaned, re.IGNORECASE) for p in _CODE_MUTATION_PATTERNS)
    has_explanation = any(re.search(p, cleaned, re.IGNORECASE) for p in _EXPLANATORY_PATTERNS)
    has_conversational = any(re.search(p, cleaned, re.IGNORECASE) for p in _CONVERSATIONAL_PATTERNS)
    has_code_entity = any(re.search(p, cleaned, re.IGNORECASE) for p in _CODE_ENTITY_PATTERNS)

    # 1. Si el usuario pide explicación sobre un archivo o código sin pedir mutaciones -> QUESTION
    if has_explanation and not has_mutation:
        return IntentType.QUESTION

    # 2. Si hay verbos explícitos de mutación o modificación de código -> CODE_TASK
    if has_mutation:
        return IntentType.CODE_TASK

    # 3. Comprobar patrones conversacionales (saludos, despedidas)
    if has_conversational and not has_code_entity:
        return IntentType.CONVERSATIONAL

    # 4. Comprobar preguntas conceptuales generales
    for pattern in _QUESTION_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE) and not has_mutation:
            return IntentType.QUESTION

    # 5. Si contiene entidades de código (archivos, rutas) -> CODE_TASK
    if has_code_entity:
        return IntentType.CODE_TASK

    # 6. Heurística para frases breves (< 25 caracteres) sin símbolos de código
    if len(cleaned) < 25 and not any(ch in cleaned for ch in "{}[]()<>=/\\;"):
        return IntentType.CONVERSATIONAL

    return IntentType.CODE_TASK
