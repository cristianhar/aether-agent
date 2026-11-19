---
name: code-review
description: Auditoría estática de calidad, complejidad ciclomática y cobertura de docstrings.
triggers: [review, code_review, audit, code-review]
---

# Code Review Skill
Esta habilidad analiza archivos de código fuente Python en busca de:
1. Funciones excesivamente largas (> 60 líneas) que requieran modularización.
2. Funciones públicas sin docstrings descriptivos.
3. Complejidad y mantenibilidad general.

## Directivas:
- Examina el código objetivo usando AST estático.
- Provee recomendaciones puntuales y accionables.
- Si detectas una función de más de 60 líneas, sugiere refactorizarla en sub-funciones auxiliares.
