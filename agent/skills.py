"""
Sistema de Habilidades Reutilizables (Skills Runtime) para AETHER IDE.
Permite ejecutar flujos especializados de revisión, debugging, refactorización y testing.
"""

import ast
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.code_intel import find_definition, find_references, get_dependencies
from tools.diagnostics import get_diagnostics


class SkillRegistry:
    """Registro y motor de ejecución de habilidades del agente."""

    @staticmethod
    def run_code_review(target_path: str = ".") -> str:
        """Habilidad: Realiza una auditoría estática de calidad, complejidad y buenas prácticas."""
        root = Path(os.path.expandvars(os.path.expanduser(target_path))).resolve()

        if root.is_file():
            files_to_check = [root]
        else:
            files_to_check = [
                f for f in root.glob("**/*.py")
                if not any(part.startswith(".") or part in ("venv", "__pycache__", "node_modules") for part in f.parts)
            ][:15]

        findings: List[str] = []

        for p in files_to_check:
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content, filename=str(p))
            except Exception as e:
                findings.append(f"❌ `{p.name}`: Error de parseo AST ({str(e)})")
                continue

            rel = p.relative_to(root) if p.is_relative_to(root) else p.name

            # Chequeos de complejidad
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines = node.end_lineno - node.lineno if hasattr(node, "end_lineno") else 0
                    if lines > 60:
                        findings.append(f"⚠️ `{rel}:{node.lineno}` Función `{node.name}` es muy extensa ({lines} líneas). Considera modularizar.")
                    # Chequeo de docstring
                    if not ast.get_docstring(node):
                        # Solo advertir si es función pública
                        if not node.name.startswith("_"):
                            findings.append(f"ℹ️ `{rel}:{node.lineno}` Función pública `{node.name}` sin docstring.")

        if not findings:
            return f"✅ **Auditoría de Código Exitosa:** No se detectaron problemas de complejidad en `{root.name}`."

        output = [f"📋 **Reporte de Code Review para `{root.name}` ({len(findings)} observaciones):**"]
        for f in findings[:20]:
            output.append(f"  • {f}")
        return "\n".join(output)

    @staticmethod
    def run_test_scaffold(module_path: str) -> str:
        """Habilidad: Genera automáticamente el esqueleto de pruebas unitarias pytest para un módulo."""
        p = Path(os.path.expandvars(os.path.expanduser(module_path))).resolve()
        if not p.is_file():
            return f"❌ Error: El archivo '{module_path}' no existe o no es un archivo Python válido."

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(p))
        except Exception as e:
            return f"❌ Error de parsing: {str(e)}"

        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")]
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

        module_stem = p.stem
        test_filename = f"test_{module_stem}.py"

        test_cases = [
            f"# Test suite generado por AETHER Skill para {p.name}",
            f"import pytest",
            f"from {module_stem} import *",
            "",
        ]

        for fn in functions:
            test_cases.append(f"def test_{fn}_basic():")
            test_cases.append(f"    # TODO: Configurar entradas de prueba para {fn}")
            test_cases.append(f"    pass\n")

        for cl in classes:
            test_cases.append(f"def test_{cl.lower()}_instance():")
            test_cases.append(f"    # TODO: Instanciar y verificar {cl}")
            test_cases.append(f"    pass\n")

        return (
            f"🧪 **Esqueleto de Pruebas Generado para `{test_filename}`:**\n\n"
            f"```python\n" + "\n".join(test_cases) + "\n```\n"
            f"👉 Usa `write_file('tests/{test_filename}', content)` para crearlo físicamente en disco."
        )


def execute_skill(skill_name: str, target: Optional[str] = None) -> str:
    """
    Despachador central de habilidades reutilizables de AETHER:
    - 'review': Auditoría estática de calidad y complejidad.
    - 'test_gen': Generación de esqueletos de tests para funciones y clases.
    - 'dependencies': Análisis del gráfico de imports y acoplamiento.
    """
    clean_skill = skill_name.lower().strip()
    target_path = target or "."

    if clean_skill in ("review", "code_review"):
        return SkillRegistry.run_code_review(target_path)
    elif clean_skill in ("test_gen", "scaffold_tests", "generate_tests"):
        return SkillRegistry.run_test_scaffold(target_path)
    elif clean_skill in ("dependencies", "deps"):
        return get_dependencies(target_path)
    else:
        return f"❌ Habilidad '{skill_name}' no reconocida. Opciones disponibles: 'review', 'test_gen', 'dependencies'."
