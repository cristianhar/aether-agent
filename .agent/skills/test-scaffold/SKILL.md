---
name: test-scaffold
description: Generador automático de esqueletos de pruebas unitarias pytest para funciones y clases.
triggers: [test_gen, test-scaffold, scaffold_tests, generate_tests]
---

# Test Scaffold Skill
Esta habilidad inspecciona el AST de un archivo Python e infiere:
1. Cada función pública (`def nombre(...)`) y genera casos de prueba `test_nombre_basic()`.
2. Cada clase pública (`class Nombre`) y genera casos de prueba de instanciación.
3. Importaciones automáticas y estructura compatible con pytest.

## Directivas:
- Genera casos de prueba limpios utilizando `pytest`.
- Emplea nombres idiomáticos (`test_<funcion>_basic`).
- Prepara los stubs listos para que el agente complete las aserciones de negocio.
