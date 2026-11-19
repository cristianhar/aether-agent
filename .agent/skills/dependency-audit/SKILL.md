---
name: dependency-audit
description: Análisis del gráfico de dependencias, acoplamiento e importaciones externas.
triggers: [dependencies, dependency-audit, deps]
---

# Dependency Audit Skill
Esta habilidad mapea las dependencias de módulos de un archivo o proyecto:
1. Módulos estándar de Python importados (e.g. os, sys, json).
2. Módulos de terceros (librerías externas en requirements/pip).
3. Importaciones locales del proyecto y análisis de acoplamiento.

## Directivas:
- Identifica dependencias críticas o circulares.
- Detecta librerías externas necesarias para la ejecución.
