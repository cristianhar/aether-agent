"""
Sistema de Habilidades Dinámicas (Skills Runtime) para AETHER IDE.
Inspirado en la especificación de Antigravity:
- Descubrimiento de carpetas con archivos SKILL.md y YAML frontmatter.
- Raíces de búsqueda en .aether/skills/, .agent/skills/ y ~/.aether/skills/.
- Soporte para ejecución estática (retrocompatibilidad) y ejecución dinámica orientada a prompts.
"""

import ast
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from tools.code_intel import get_dependencies


@dataclass
class SkillDefinition:
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    instructions: str = ""
    skill_dir: Optional[Path] = None
    skill_file: Optional[Path] = None
    is_dynamic: bool = True


def parse_frontmatter_markdown(content: str) -> tuple[Dict[str, Any], str]:
    """
    Parsea de forma segura el bloque frontmatter YAML entre '---' y devuelve (metadata, body_markdown).
    Maneja parsing robusto sin requerir paquetes externos adicionales.
    """
    pattern = r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$"
    match = re.match(pattern, content.strip(), re.DOTALL)
    if not match:
        return {}, content.strip()

    front_text, body = match.group(1), match.group(2)
    meta: Dict[str, Any] = {}

    for line in front_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                meta[key] = items
            elif val.lower() in ("true", "yes"):
                meta[key] = True
            elif val.lower() in ("false", "no"):
                meta[key] = False
            elif val.isdigit():
                meta[key] = int(val)
            else:
                meta[key] = val.strip("'\"")

    return meta, body.strip()


class SkillRegistry:
    """Registro y motor de ejecución de habilidades del agente (Estáticas y Dinámicas)."""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.skills: Dict[str, SkillDefinition] = {}
        self.reload_skills()

    def reload_skills(self):
        """Descubre automáticamente todas las skills en las raíces estándar del proyecto."""
        self.skills.clear()

        discovery_paths = [
            self.workspace_root / ".aether" / "skills",
            self.workspace_root / ".agent" / "skills",
            Path.home() / ".aether" / "skills",
        ]

        for base_dir in discovery_paths:
            if not base_dir.exists() or not base_dir.is_dir():
                continue
            for skill_file in base_dir.glob("**/SKILL.md"):
                try:
                    content = skill_file.read_text(encoding="utf-8", errors="replace")
                    meta, body = parse_frontmatter_markdown(content)
                    skill_name = meta.get("name", skill_file.parent.name).lower().strip()
                    triggers = meta.get("triggers", [skill_name])
                    if isinstance(triggers, str):
                        triggers = [triggers]

                    self.skills[skill_name] = SkillDefinition(
                        name=skill_name,
                        description=meta.get("description", f"Habilidad especializada {skill_name}"),
                        triggers=triggers,
                        instructions=body,
                        skill_dir=skill_file.parent,
                        skill_file=skill_file,
                        is_dynamic=True,
                    )
                except Exception:
                    continue

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Obtiene una skill por su nombre o alias registrado."""
        clean = name.lower().strip()
        if clean in self.skills:
            return self.skills[clean]
        for sk in self.skills.values():
            if clean in [t.lower() for t in sk.triggers]:
                return sk
        return None

    def match_skill(self, user_query: str) -> Optional[SkillDefinition]:
        """Encuentra la skill más relevante para una consulta o intención del usuario."""
        query_lower = user_query.lower()
        for sk in self.skills.values():
            for trigger in sk.triggers:
                if trigger.lower() in query_lower:
                    return sk
        return None

    def get_skills_catalog_prompt(self) -> str:
        """Genera el bloque de documentación de skills para inyectar en el System Prompt."""
        if not self.skills:
            return ""

        lines = ["## Habilidades Especializadas Disponibles (Skills):"]
        for sk in sorted(self.skills.values(), key=lambda s: s.name):
            file_loc = str(sk.skill_file.relative_to(self.workspace_root)).replace("\\", "/") if sk.skill_file else sk.name
            lines.append(f"- **{sk.name}** (`{file_loc}`): {sk.description}")
        lines.append("Para utilizar cualquiera de estas habilidades especializadas, invoca 'execute_skill(skill_name=\"...\")'.")
        return "\n".join(lines)

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

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines = node.end_lineno - node.lineno if hasattr(node, "end_lineno") else 0
                    if lines > 60:
                        findings.append(f"⚠️ `{rel}:{node.lineno}` Función `{node.name}` es muy extensa ({lines} líneas). Considera modularizar.")
                    if not ast.get_docstring(node):
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
            "import pytest",
            f"from {module_stem} import *",
            "",
        ]

        for fn in functions:
            test_cases.append(f"def test_{fn}_basic():")
            test_cases.append(f"    # TODO: Configurar entradas de prueba para {fn}")
            test_cases.append("    pass\n")

        for cl in classes:
            test_cases.append(f"def test_{cl.lower()}_instance():")
            test_cases.append(f"    # TODO: Instanciar y verificar {cl}")
            test_cases.append("    pass\n")

        return (
            f"🧪 **Esqueleto de Pruebas Generado para `{test_filename}`:**\n\n"
            f"```python\n" + "\n".join(test_cases) + "\n```\n"
            f"👉 Usa `write_file('tests/{test_filename}', content)` para crearlo físicamente en disco."
        )


_GLOBAL_SKILL_REGISTRY: Optional[SkillRegistry] = None


def get_global_skill_registry(workspace_root: Optional[Path] = None, force_reload: bool = False) -> SkillRegistry:
    global _GLOBAL_SKILL_REGISTRY
    req_root = Path(workspace_root).resolve() if workspace_root else None
    if _GLOBAL_SKILL_REGISTRY is None or force_reload or (req_root and _GLOBAL_SKILL_REGISTRY.workspace_root != req_root):
        _GLOBAL_SKILL_REGISTRY = SkillRegistry(workspace_root)
    return _GLOBAL_SKILL_REGISTRY


def execute_skill(skill_name: str, target: Optional[str] = None) -> str:
    """
    Despachador universal de habilidades de AETHER:
    - Ejecuta habilidades estáticas (review, test_gen, dependencies).
    - Ejecuta habilidades dinámicas descubiertas en carpetas SKILL.md.
    """
    clean_skill = skill_name.lower().strip()
    target_path = target or "."

    # 1. Habilidades estáticas nativas
    if clean_skill in ("review", "code_review", "code-review"):
        return SkillRegistry.run_code_review(target_path)
    elif clean_skill in ("test_gen", "scaffold_tests", "generate_tests", "test-scaffold"):
        return SkillRegistry.run_test_scaffold(target_path)
    elif clean_skill in ("dependencies", "deps", "dependency-audit"):
        return get_dependencies(target_path)

    # 2. Búsqueda en el catálogo dinámico de SKILL.md
    registry = get_global_skill_registry()
    sk = registry.get_skill(clean_skill)
    if sk:
        header = f"🛠️ **Habilidad Activa: [{sk.name.upper()}]**\n{sk.description}\n\n"
        body = f"---\n### Directivas de Ejecución:\n{sk.instructions}"
        return header + body

    available = ["review", "test_gen", "dependencies"] + list(registry.skills.keys())
    return f"❌ Habilidad '{skill_name}' no reconocida. Opciones disponibles: {', '.join(sorted(set(available)))}."
