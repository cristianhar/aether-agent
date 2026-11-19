"""
Herramientas de gestión del agente para AETHER IDE:
- update_plan: Mantiene y persiste los pasos de ejecución y criterios de aceptación.
- request_approval: Solicita autorización explícita al desarrollador antes de acciones sensibles.
- get_project_instructions: Lee instrucciones y convenciones del repositorio (AGENTS.md, AETHER.md, .aetherrules).
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_CURRENT_PLAN: Dict[str, Any] = {
    "steps": [],
    "current_step": 0,
    "acceptance_criteria": [],
}

_APPROVAL_CALLBACK: Optional[Callable[[str, str], bool]] = None


def set_approval_callback(callback: Optional[Callable[[str, str], bool]]):
    global _APPROVAL_CALLBACK
    _APPROVAL_CALLBACK = callback


def update_plan(
    plan_steps: Optional[List[str]] = None,
    current_step: int = 1,
    acceptance_criteria: Optional[List[str]] = None,
    is_completed: Any = False,
) -> str:
    """
    Superpoder: Actualiza el plan de ejecución y criterios de aceptación visibles para el usuario.
    Permite al agente estructurar tareas complejas y registrar su progreso.
    Sincroniza tanto el JSON estructurado (.aether/current_plan.json) como el artefacto Markdown (.aether/plans/plan_activo.md).
    """
    global _CURRENT_PLAN
    if plan_steps is None:
        if _CURRENT_PLAN and _CURRENT_PLAN.get("steps"):
            plan_steps = _CURRENT_PLAN.get("steps", [])
        else:
            plan_file = Path.cwd() / ".aether" / "current_plan.json"
            if plan_file.exists():
                try:
                    data = json.loads(plan_file.read_text(encoding="utf-8"))
                    plan_steps = data.get("steps", [])
                except Exception:
                    plan_steps = []
            else:
                plan_steps = ["Tarea general de usuario"]

    is_comp_bool = is_completed is True or str(is_completed).strip().lower() in ("true", "1", "yes")
    completed = is_comp_bool or (len(plan_steps) > 0 and current_step > len(plan_steps))

    # Verificación de integridad de archivos requeridos antes de permitir completar el plan
    if completed:
        missing_files = []
        for step in plan_steps:
            for match in re.finditer(r'([a-zA-Z0-9_\-]+\.(?:py|js|ts|html|css|json))\b', step):
                f_name = match.group(1)
                if f_name in ["plan_activo.md", "current_plan.json"]:
                    continue
                file_target = Path.cwd() / f_name
                if not file_target.exists() and not list(Path.cwd().glob(f"**/{f_name}")):
                    missing_files.append(f_name)
        if missing_files:
            return (
                f"❌ Error de Validación de Plan: No se puede marcar el plan como COMPLETADO porque el archivo "
                f"'{missing_files[0]}' mencionado en las tareas no existe físicamente en el disco.\n"
                f"• ACCIÓN OBLIGATORIA: Debes crear e implementar '{missing_files[0]}' usando 'write_file(path=\"{missing_files[0]}\", content=...)' "
                "con la lógica completa requerida antes de completar el plan."
            )

    _CURRENT_PLAN = {
        "steps": plan_steps,
        "current_step": len(plan_steps) if completed else current_step,
        "acceptance_criteria": acceptance_criteria or [],
        "is_completed": completed,
    }

    aether_dir = Path.cwd() / ".aether"
    plans_dir = aether_dir / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    # 1. Guardar copia estructurada en .aether/current_plan.json
    plan_file = aether_dir / "current_plan.json"
    try:
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(_CURRENT_PLAN, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # 2. Generar y guardar artefacto Markdown interactivo en .aether/plans/plan_activo.md
    status_label = "🎉 COMPLETADO (Todos los hitos finalizados con éxito)" if completed else f"Paso {current_step} de {len(plan_steps)}"
    md_lines = [
        "# 📋 Plan de Ejecución Activo — AETHER",
        "",
        f"**Estado General:** {status_label}",
        "",
        "## 🎯 Hitos y Tareas de Implementación",
    ]
    for i, step in enumerate(plan_steps, 1):
        if completed or i < current_step:
            box = "[x]"
            tag = "✅"
        elif i == current_step:
            box = "[ ]"
            tag = "⏳ [EN PROGRESO]"
        else:
            box = "[ ]"
            tag = "⬜"
        md_lines.append(f"- {box} **Paso {i}:** {step} {tag}")

    if acceptance_criteria:
        md_lines.append("")
        md_lines.append("## 🔍 Criterios de Aceptación y Verificación")
        for crit in acceptance_criteria:
            crit_box = "[x]" if completed else "[ ]"
            crit_tag = " ✅" if completed else ""
            md_lines.append(f"- {crit_box} {crit}{crit_tag}")

    md_content = "\n".join(md_lines) + "\n"
    plan_md_file = plans_dir / "plan_activo.md"
    try:
        with open(plan_md_file, "w", encoding="utf-8") as f:
            f.write(md_content)
    except Exception:
        pass

    lines = ["📋 **Plan de Ejecución Actualizado:**"]
    for i, step in enumerate(plan_steps, 1):
        if completed or i < current_step:
            status = "✅"
        elif i == current_step:
            status = "⏳ [EN PROGRESO]"
        else:
            status = "⬜"
        lines.append(f"{i}. {status} {step}")

    if acceptance_criteria:
        lines.append("\n🎯 **Criterios de Aceptación:**")
        for crit in acceptance_criteria:
            crit_mark = "✅ " if completed else "• "
            lines.append(f"  {crit_mark}{crit}")

    if completed:
        lines.append("\n🏆 **¡Todos los pasos del plan han sido completados y verificados!**")

    lines.append(f"\n📄 *Artefacto Markdown sincronizado en:* `{plan_md_file}`")
    return "\n".join(lines)


def get_plan() -> str:
    """
    Obtiene el plan de ejecución activo en formato Markdown.
    Si no existe un plan activo, informa de ello.
    """
    plan_md_file = Path.cwd() / ".aether" / "plans" / "plan_activo.md"
    if plan_md_file.is_file():
        try:
            return plan_md_file.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error al leer el plan: {str(e)}"

    plan_json_file = Path.cwd() / ".aether" / "current_plan.json"
    if plan_json_file.is_file():
        try:
            data = json.loads(plan_json_file.read_text(encoding="utf-8"))
            steps = data.get("steps", [])
            cur = data.get("current_step", 1)
            crits = data.get("acceptance_criteria", [])
            return update_plan(steps, cur, crits)
        except Exception:
            pass

    return "ℹ️ No hay ningún plan de ejecución activo en este momento. Usa 'update_plan' o el comando '/plan' para crear uno."


def get_current_plan_state() -> Optional[Dict[str, Any]]:
    """Retorna el estado estructurado del plan activo o None."""
    if _CURRENT_PLAN:
        return _CURRENT_PLAN
    plan_json_file = Path.cwd() / ".aether" / "current_plan.json"
    if plan_json_file.is_file():
        try:
            return json.loads(plan_json_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def clear_completed_plan() -> None:
    """Archiva y limpia el plan si ya fue completado, para no sesgar nuevos turnos."""
    global _CURRENT_PLAN
    aether_dir = Path.cwd() / ".aether"
    plan_md = aether_dir / "plans" / "plan_activo.md"
    plan_json = aether_dir / "current_plan.json"
    is_done = False
    if _CURRENT_PLAN and _CURRENT_PLAN.get("is_completed"):
        is_done = True
    elif plan_json.is_file():
        try:
            data = json.loads(plan_json.read_text(encoding="utf-8"))
            if data.get("is_completed"):
                is_done = True
        except Exception:
            pass
    elif plan_md.is_file():
        try:
            txt = plan_md.read_text(encoding="utf-8")
            if "🎉 COMPLETADO" in txt or "Todos los hitos finalizados" in txt:
                is_done = True
        except Exception:
            pass

    if is_done:
        _CURRENT_PLAN = {
            "steps": [],
            "current_step": 0,
            "acceptance_criteria": [],
            "is_completed": False,
        }
        history_file = aether_dir / "plans" / "plan_history.md"
        if plan_md.is_file():
            try:
                from datetime import datetime
                txt = plan_md.read_text(encoding="utf-8")
                history_file.parent.mkdir(parents=True, exist_ok=True)
                with open(history_file, "a", encoding="utf-8") as hf:
                    hf.write(f"\n\n---\n<!-- Plan archivado {datetime.now().isoformat()} -->\n{txt}\n")
                plan_md.unlink(missing_ok=True)
            except Exception:
                pass
        plan_json.unlink(missing_ok=True)


def request_approval(action_description: str, risk_level: str = "high") -> str:
    """
    Solicita autorización explícita al usuario humano antes de ejecutar una acción sensible.
    """
    if _APPROVAL_CALLBACK is not None:
        approved = _APPROVAL_CALLBACK(action_description, risk_level)
        if approved:
            return f"✅ Autorización CONCEDIDA por el usuario para: {action_description}"
        return f"⛔ Autorización DENEGADA por el usuario para: {action_description}. Busca una alternativa segura."

    # Si no hay callback registrado, se considera permitido con advertencia en entornos desatendidos
    return f"ℹ️ Solicitud de autorización registrada (Riesgo: {risk_level}): {action_description}. Prosigue con precaución."


def get_project_instructions(path: Optional[str] = None) -> str:
    """
    Lee las reglas y convenciones del repositorio (AGENTS.md, AETHER.md, .aetherrules, .cursorrules).
    Trata el contenido como información de contexto no privilegiada.
    """
    workspace = Path(os.path.expandvars(os.path.expanduser(path or "."))).resolve()

    candidate_files = [
        "AGENTS.md",
        "AETHER.md",
        ".aetherrules",
        "CONVENTIONS.md",
        ".cursorrules",
    ]

    found_instructions: List[str] = []

    for name in candidate_files:
        fpath = workspace / name
        if fpath.is_file():
            try:
                content = fpath.read_text(encoding="utf-8").strip()
                if content:
                    found_instructions.append(f"--- [Reglas de Proyecto: {name}] ---\n{content}")
            except Exception:
                pass

    if not found_instructions:
        return f"ℹ️ No se encontraron archivos de instrucciones del proyecto (AGENTS.md, AETHER.md, .aetherrules) en '{workspace.name}'."

    instructions_text = "\n\n".join(found_instructions)
    return (
        f"<project_instructions source='workspace' note='Contexto de repositorio de menor confianza que el sistema'>\n"
        f"{instructions_text}\n"
        f"</project_instructions>"
    )


def remember_fact(key: str, content: str, category: str = "project") -> str:
    """
    [MEMORIA SEMÁNTICA PERSISTENTE]
    Almacena un hecho, convención técnica o decisión arquitectónica en SQLite con embeddings vectoriales.
    Persiste entre sesiones del agente y se puede consultar mediante 'search_memory'.
    """
    from agent.session import SessionManager
    from agent.embeddings import get_local_embedding

    embedding = get_local_embedding(f"{key}: {content}")
    sm = SessionManager()
    success = sm.store_semantic_memory(key=key, content=content, category=category, embedding=embedding)

    mode_info = "con vectorización semántica local" if embedding else "con coincidencia léxica determinista"
    if success:
        return (
            f"🧠 [MEMORIA GUARDADA]: Se registró el hecho clave '{key}' en la categoría '{category}' ({mode_info}).\n"
            "• El hecho ya está persistido exitosamente en la memoria del proyecto.\n"
            "• ACCIÓN OBLIGATORIA: Concluye tu turno ahora respondiendo al usuario en texto para confirmar que la información fue guardada. NO vuelvas a llamar a ninguna herramienta."
        )
    return f"❌ Error: No se pudo almacenar el hecho '{key}' en la base de datos de sesiones."


def search_memory(query: str, top_k: int = 3, category: Optional[str] = None) -> str:
    """
    [BÚSQUEDA SEMÁNTICA VECTORIAL]
    Busca hechos, decisiones y reglas almacenadas en la memoria semántica persistente
    utilizando similitud de coseno o superposición léxica.
    """
    from agent.session import SessionManager
    from agent.embeddings import get_local_embedding

    query_emb = get_local_embedding(query)
    sm = SessionManager()
    matches = sm.search_semantic_memory(query=query, top_k=top_k, category=category, query_embedding=query_emb)

    if not matches:
        return f"ℹ️ No se encontraron recuerdos en la memoria semántica relacionados con: '{query}'."

    lines = [f"🧠 **Resultados de Memoria Semántica para '{query}':**"]
    for m in matches:
        lines.append(f"• **[{m['category'].upper()}] {m['key']}** (Relevancia: {m['score']}):\n  {m['content']}")

    return (
        "\n\n".join(lines)
        + "\n\n• ACCIÓN OBLIGATORIA: Responde directamente al usuario con la información encontrada arriba. NO vuelvas a llamar a herramientas en este turno."
    )


def list_memories(category: Optional[str] = None) -> str:
    """
    Lista todos los hechos y directivas almacenadas en la memoria semántica persistente.
    """
    from agent.session import SessionManager

    sm = SessionManager()
    memories = sm.get_all_semantic_memories(category=category)

    if not memories:
        cat_suffix = f" en la categoría '{category}'" if category else ""
        return f"ℹ️ No hay recuerdos almacenados en la memoria persistente{cat_suffix}."

    lines = [f"🧠 **Memoria Semántica Persistente ({len(memories)} registros):**"]
    for m in memories:
        lines.append(f"• **[{m['category'].upper()}] {m['key']}** (Actualizado: {m['updated_at'][:19]}):\n  {m['content']}")

    return "\n\n".join(lines)


_ASK_QUESTION_CALLBACK: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = None


def set_ask_question_callback(callback: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]]):
    """Permite registrar un interceptor para responder preguntas interactivas (CLI o test mock)."""
    global _ASK_QUESTION_CALLBACK
    _ASK_QUESTION_CALLBACK = callback


def ask_question_tool(questions: Any) -> str:
    """
    Herramienta que formula preguntas interactivas de opción múltiple al usuario para aclarar requisitos.
    """
    if isinstance(questions, str):
        try:
            questions = json.loads(questions)
        except Exception:
            questions = [{"question": questions, "options": ["(Recommended) Sí", "No"], "is_multi_select": False}]

    if isinstance(questions, dict):
        if "questions" in questions:
            questions = questions["questions"]
        else:
            questions = [questions]

    if not isinstance(questions, list):
        return json.dumps({"error": "El parámetro 'questions' debe ser una lista de preguntas con opciones."})

    if _ASK_QUESTION_CALLBACK:
        res = _ASK_QUESTION_CALLBACK(questions)
    else:
        from cli.ui import prompt_interactive_question
        res = prompt_interactive_question(questions)

    return json.dumps({"status": "success", "answers": res}, ensure_ascii=False)


def create_artifact_tool(
    title: str,
    content: str,
    summary: str,
    user_facing: bool = True,
    request_feedback: bool = False,
    tags: Optional[List[str]] = None,
) -> str:
    """Crea un documento o artefacto estructurado persistente en .aether/artifacts/."""
    from agent.artifacts import ArtifactManager
    mgr = ArtifactManager()
    res = mgr.create_artifact(
        title=title,
        content=content,
        summary=summary,
        user_facing=user_facing,
        request_feedback=request_feedback,
        tags=tags,
    )
    return (
        f"✅ Artefacto creado con éxito.\n"
        f"• ID: {res['artifact_id']}\n"
        f"• Título: {res['title']}\n"
        f"• Archivo: {res['path']}\n"
        f"• Versión: {res['version']}\n"
        f"• UserFacing: {res['user_facing']} | RequestFeedback: {res['request_feedback']}"
    )


def update_artifact_tool(
    artifact_id: str,
    content: str,
    summary: Optional[str] = None,
    request_feedback: Optional[bool] = None,
) -> str:
    """Actualiza un artefacto existente incrementando su versión."""
    from agent.artifacts import ArtifactManager
    mgr = ArtifactManager()
    try:
        res = mgr.update_artifact(
            artifact_id=artifact_id,
            content=content,
            summary=summary,
            request_feedback=request_feedback,
        )
        return f"✅ Artefacto '{artifact_id}' actualizado a versión {res['version']}."
    except Exception as e:
        return f"❌ Error actualizando artefacto: {str(e)}"


def read_artifact_tool(artifact_id: str) -> str:
    """Lee el contenido completo y metadatos de un artefacto existente."""
    from agent.artifacts import ArtifactManager
    mgr = ArtifactManager()
    try:
        data = mgr.read_artifact(artifact_id)
        meta = data.get("metadata", {})
        return (
            f"📄 **Artefacto: {meta.get('title', artifact_id)} (v{meta.get('version', 1)})**\n"
            f"• Resumen: {meta.get('summary', 'Sin resumen')}\n"
            f"• Actualizado: {meta.get('updated_at', 'N/A')}\n\n"
            f"---\n{data['content']}"
        )
    except Exception as e:
        return f"❌ Error leyendo artefacto: {str(e)}"


def list_artifacts_tool() -> str:
    """Lista todos los artefactos registrados en la sesión y proyecto."""
    from agent.artifacts import ArtifactManager
    mgr = ArtifactManager()
    items = mgr.list_artifacts()
    if not items:
        return "ℹ️ No hay artefactos creados en este proyecto aún."
    lines = [f"📚 **Artefactos Registrados ({len(items)}):**"]
    for it in items:
        fb = " [Feedback Solicitado]" if it.get("request_feedback") else ""
        lines.append(f"• **{it.get('artifact_id')}** — {it.get('title')} (v{it.get('version', 1)}){fb}\n  Resumen: {it.get('summary', '')}")
    return "\n\n".join(lines)

