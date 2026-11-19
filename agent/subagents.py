"""
Sistema Jerárquico de Subagentes y Buzón de Mensajería para AETHER IDE.
Inspirado en la arquitectura de Antigravity (Google DeepMind):
- Definición dinámica de subagentes en runtime (`define_subagent`).
- Invocación con aislamiento de memoria de tokens (`invoke_subagent`).
- Buzón bidireccional reactivo de mensajes (`send_message`).
- Gestión de ciclo de vida (`manage_subagents`: list, status, kill, kill_all).
- Aislamiento de workspace ('inherit' y 'branch').
"""

from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
import shutil
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from agent.hooks import HookManager
from agent.prompts import get_system_prompt
from agent.state import AgentState


@dataclass
class SubagentTemplate:
    """Plantilla de definición para un tipo de subagente."""
    name: str
    description: str
    system_prompt: str
    enable_write_tools: bool = True
    enable_subagent_tools: bool = False
    enable_mcp_tools: bool = False


@dataclass
class MailboxMessage:
    """Mensaje intercambiado en el buzón entre agentes."""
    sender: str
    recipient: str
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SubagentInstance:
    """Instancia viva de un subagente con su propio contexto de ejecución."""
    conversation_id: str
    type_name: str
    role: str
    workspace_mode: str
    workspace_dir: Path
    model: str
    orchestrator: Any
    enable_write_tools: bool
    status: str = "idle"  # idle, running, completed, error, terminated
    inbox: List[MailboxMessage] = field(default_factory=list)
    outbox: List[MailboxMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    is_killed: bool = False


class SubagentManager:
    """
    Gestor central de subagentes jerárquicos y buzón de mensajería reactivo.
    """

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.templates: Dict[str, SubagentTemplate] = {}
        self.instances: Dict[str, SubagentInstance] = {}
        self._register_default_templates()

    def _register_default_templates(self):
        """Registra los tipos de subagentes predeterminados del sistema."""
        self.templates["research"] = SubagentTemplate(
            name="research",
            description="Subagente investigador de solo lectura para explorar el repositorio y responder dudas sin mutar disco.",
            system_prompt=(
                "Eres el Subagente Investigador (Research) de AETHER. Operas en MODO ASK (Solo Lectura). "
                "Tu propósito es explorar código, analizar dependencias y responder con precisión técnica "
                "sin modificar ni crear ningún archivo en disco."
            ),
            enable_write_tools=False,
            enable_subagent_tools=False,
            enable_mcp_tools=False,
        )

        self.templates["self"] = SubagentTemplate(
            name="self",
            description="Subagente autónomo con capacidades completas que hereda la configuración general del agente principal.",
            system_prompt=(
                "Eres un Subagente autónomo de desarrollo para AETHER IDE. "
                "Resuelve la tarea delegada de forma proactiva, quirúrgica y exhaustiva. "
                "Al finalizar, presenta un informe técnico claro con los cambios o resultados."
            ),
            enable_write_tools=True,
            enable_subagent_tools=False,
            enable_mcp_tools=False,
        )

        self.templates["tester"] = SubagentTemplate(
            name="tester",
            description="Subagente auditor de pruebas para ejecutar suites de tests y diagnosticar stack traces de fallo.",
            system_prompt=(
                "Eres el Subagente Auditor de Pruebas de AETHER. "
                "Tu objetivo es ejecutar los comandos de test requeridos, analizar los resultados "
                "y reportar diagnósticos claros de errores si los hubiera."
            ),
            enable_write_tools=True,
            enable_subagent_tools=False,
            enable_mcp_tools=False,
        )

    def define_subagent(
        self,
        name: str,
        description: str,
        system_prompt: str,
        enable_write_tools: bool = True,
        enable_subagent_tools: bool = False,
        enable_mcp_tools: bool = False,
    ) -> str:
        """Define o actualiza un tipo de subagente reutilizable en tiempo de ejecución."""
        clean_name = name.lower().strip()
        if not clean_name:
            return "❌ Error: El nombre del subagente no puede estar vacío."

        self.templates[clean_name] = SubagentTemplate(
            name=clean_name,
            description=description.strip(),
            system_prompt=system_prompt.strip(),
            enable_write_tools=enable_write_tools,
            enable_subagent_tools=enable_subagent_tools,
            enable_mcp_tools=enable_mcp_tools,
        )
        mode_desc = "Lectura y Escritura" if enable_write_tools else "Solo Lectura (Modo ASK)"
        return (
            f"✅ Subagente tipo '{clean_name}' registrado exitosamente.\n"
            f"• Rol: {description}\n"
            f"• Permisos: {mode_desc}\n"
            f"• Subagentes anidados: {'Sí' if enable_subagent_tools else 'No'}\n"
            f"👉 Puedes invocarlo usando `invoke_subagent(type_name='{clean_name}', ...)`."
        )

    def invoke_subagent(
        self,
        type_name: str,
        role: str,
        prompt: str,
        workspace: str = "inherit",
        model: Optional[str] = None,
        max_iterations: int = 8,
    ) -> str:
        """
        Instancia y ejecuta un subagente en un contexto aislado con su propio buzón.
        Devuelve el conversation_id y el resultado inicial de la tarea.
        """
        from agent.orchestrator import AgentOrchestrator

        clean_type = type_name.lower().strip()
        template = self.templates.get(clean_type)
        if not template:
            # Fallback transparente al template 'self'
            template = SubagentTemplate(
                name=clean_type,
                description=f"Subagente dinámico: {role}",
                system_prompt=f"Eres un subagente de AETHER con el rol: {role}.\nEjecuta la siguiente misión delegada.",
                enable_write_tools=True,
            )

        conversation_id = f"sub-{uuid.uuid4().hex[:8]}"

        # Configuración de workspace
        mode_workspace = workspace.lower().strip()
        if mode_workspace == "branch":
            sub_workspace = self.workspace_root / ".aether" / "workspaces" / conversation_id
            sub_workspace.mkdir(parents=True, exist_ok=True)
        else:
            sub_workspace = self.workspace_root

        sub_model = model or "qwen2.5-coder:7b"
        operating_mode = "agent" if template.enable_write_tools else "ask"

        orchestrator = AgentOrchestrator(
            model=sub_model,
            system_prompt=template.system_prompt,
            max_iterations=max_iterations,
            mode=operating_mode,
        )
        # Asegurar hooks de permisos adecuados
        orchestrator.hooks = HookManager(mode=operating_mode)

        instance = SubagentInstance(
            conversation_id=conversation_id,
            type_name=clean_type,
            role=role,
            workspace_mode=mode_workspace,
            workspace_dir=sub_workspace,
            model=sub_model,
            orchestrator=orchestrator,
            enable_write_tools=template.enable_write_tools,
            status="running",
        )
        self.instances[conversation_id] = instance

        # Enviar mensaje al buzón de entrada
        msg_in = MailboxMessage(sender="coordinator", recipient=conversation_id, content=prompt)
        instance.inbox.append(msg_in)

        try:
            report = orchestrator.run_turn(prompt)
            instance.status = "idle"
            msg_out = MailboxMessage(sender=conversation_id, recipient="coordinator", content=report)
            instance.outbox.append(msg_out)

            header = (
                f"🤖 **Subagente Activado: [{role}]**\n"
                f"• ID Conversación: `{conversation_id}`\n"
                f"• Tipo: `{clean_type}` | Modo: `{operating_mode.upper()}` | Workspace: `{mode_workspace}`\n\n"
            )
            return f"{header}=== RESULTADO DEL SUBAGENTE ===\n{report}"
        except Exception as e:
            instance.status = "error"
            return f"❌ Error ejecutando subagente `{conversation_id}` ({role}): {str(e)}"

    def send_message(self, recipient: str, message: str) -> str:
        """
        Envía un mensaje de seguimiento al buzón de un subagente existente
        y ejecuta un nuevo turno conservando el historial previo de su conversación.
        """
        target_id = recipient.strip()
        instance = self.instances.get(target_id)
        if not instance:
            return f"❌ Error: No se encontró ningún subagente con el ID de conversación `{target_id}`."

        if instance.is_killed or instance.status == "terminated":
            return f"❌ Error: El subagente `{target_id}` ha sido terminado y ya no puede recibir mensajes."

        msg_in = MailboxMessage(sender="coordinator", recipient=target_id, content=message)
        instance.inbox.append(msg_in)
        instance.status = "running"

        try:
            reply = instance.orchestrator.run_turn(message)
            instance.status = "idle"
            msg_out = MailboxMessage(sender=target_id, recipient="coordinator", content=reply)
            instance.outbox.append(msg_out)

            return (
                f"📬 **Respuesta del Subagente `{target_id}` [{instance.role}]:**\n\n"
                f"{reply}"
            )
        except Exception as e:
            instance.status = "error"
            return f"❌ Error comunicando con subagente `{target_id}`: {str(e)}"

    def manage_subagents(self, action: str, conversation_ids: Optional[List[str]] = None) -> str:
        """
        Administra el ciclo de vida de los subagentes activos:
        - 'list': Reporta todos los subagentes y sus estados.
        - 'status': Detalla un subagente y su buzón de mensajes.
        - 'kill': Termina permanentemente subagentes especificados y limpia workspaces branch.
        - 'kill_all': Termina todos los subagentes activos.
        """
        act = action.lower().strip()

        if act == "list":
            if not self.instances:
                return "ℹ️ No hay subagentes activos ni registrados en esta sesión."

            lines = ["📋 **Directorio de Subagentes:**", ""]
            for cid, inst in self.instances.items():
                status_icon = {
                    "idle": "💤 Idle",
                    "running": "⚡ Running",
                    "completed": "✅ Completed",
                    "error": "❌ Error",
                    "terminated": "🛑 Terminated",
                }.get(inst.status, inst.status)
                lines.append(
                    f"- `{cid}`: **{inst.role}** (Tipo: `{inst.type_name}`) | Estado: {status_icon} | "
                    f"Workspace: `{inst.workspace_mode}` | Mensajes: {len(inst.inbox)} recibidos, {len(inst.outbox)} emitidos"
                )
            return "\n".join(lines)

        elif act == "status":
            ids = conversation_ids or list(self.instances.keys())
            if not ids:
                return "ℹ️ No hay subagentes registrados."

            sections = []
            for cid in ids:
                inst = self.instances.get(cid)
                if not inst:
                    sections.append(f"❌ Subagente `{cid}` no encontrado.")
                    continue

                sec = [
                    f"### Subagente `{cid}` — {inst.role}",
                    f"- **Tipo:** {inst.type_name}",
                    f"- **Estado:** {inst.status}",
                    f"- **Workspace:** `{inst.workspace_mode}` ({inst.workspace_dir})",
                    f"- **Herramientas de Escritura:** {'Habilitadas' if inst.enable_write_tools else 'Bloqueadas (Solo Lectura)'}",
                    f"- **Historial de Mensajes ({len(inst.inbox)} entradas, {len(inst.outbox)} salidas):**",
                ]
                for idx, (m_in, m_out) in enumerate(zip(inst.inbox, inst.outbox), 1):
                    sec.append(f"  * [Turno {idx} Entrante]: {m_in.content[:80]}...")
                    sec.append(f"  * [Turno {idx} Respuesta]: {m_out.content[:80]}...")
                sections.append("\n".join(sec))

            return "\n\n".join(sections)

        elif act in ["kill", "terminate"]:
            target_ids = conversation_ids or []
            if not target_ids:
                return "⚠️ Debes especificar los `conversation_ids` a terminar."

            killed = []
            for cid in target_ids:
                inst = self.instances.get(cid)
                if inst:
                    inst.status = "terminated"
                    inst.is_killed = True
                    # Limpieza segura si es workspace en rama aislada
                    if inst.workspace_mode == "branch" and inst.workspace_dir.exists():
                        try:
                            shutil.rmtree(inst.workspace_dir, ignore_errors=True)
                        except Exception:
                            pass
                    killed.append(cid)

            return f"🛑 Subagentes terminados: {', '.join(killed) if killed else 'Ninguno encontrado'}."

        elif act in ["kill_all", "terminate_all"]:
            count = 0
            for cid, inst in self.instances.items():
                if not inst.is_killed:
                    inst.status = "terminated"
                    inst.is_killed = True
                    if inst.workspace_mode == "branch" and inst.workspace_dir.exists():
                        try:
                            shutil.rmtree(inst.workspace_dir, ignore_errors=True)
                        except Exception:
                            pass
                    count += 1
            return f"🛑 Se terminaron todos los subagentes activos ({count} subagentes finalizados)."

        else:
            return f"❌ Acción de gestión '{action}' desconocida. Opciones: 'list', 'status', 'kill', 'kill_all'."


_GLOBAL_SUBAGENT_MANAGER: Optional[SubagentManager] = None


def get_global_subagent_manager(workspace_root: Optional[Path] = None, force_reload: bool = False) -> SubagentManager:
    """Obtiene o inicializa el gestor global de subagentes."""
    global _GLOBAL_SUBAGENT_MANAGER
    req_root = Path(workspace_root).resolve() if workspace_root else None
    if _GLOBAL_SUBAGENT_MANAGER is None or force_reload or (req_root and _GLOBAL_SUBAGENT_MANAGER.workspace_root != req_root):
        _GLOBAL_SUBAGENT_MANAGER = SubagentManager(workspace_root)
    return _GLOBAL_SUBAGENT_MANAGER
