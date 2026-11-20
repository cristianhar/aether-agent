import React, { useState, useEffect, useRef } from "react";
import Editor, { DiffEditor } from "@monaco-editor/react";
import {
  FileCode,
  Play,
  RotateCcw,
  Sparkles,
  GitBranch,
  Cpu,
  Save,
  Square,
  RefreshCw,
  FolderTree,
  FileText,
  Search,
  Code2,
  Terminal,
  ShieldCheck,
  ShieldAlert,
  Shield,
  Trash2,
  Columns,
  Package,
  Globe,
  HelpCircle,
  Layers,
  Send,
  Bot,
} from "lucide-react";
import "./App.css";

const BRIDGE_URL = "http://127.0.0.1:8765";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  isCommand?: boolean;
}

interface SlashCommand {
  cmd: string;
  label: string;
  desc: string;
  icon: React.ReactNode;
}

interface QuestionItem {
  question: string;
  options: string[];
  is_multi_select?: boolean;
}

interface ArtifactItem {
  id: string;
  type: string;
  title: string;
  created_at: string;
  summary?: string;
}

const SLASH_COMMANDS: SlashCommand[] = [
  { cmd: "/mode agent", label: "/mode agent", desc: "Modo Autónomo Total (lectura, escritura y comandos)", icon: <ShieldCheck size={14} color="#10b981" /> },
  { cmd: "/mode ask", label: "/mode ask", desc: "Modo Seguro (requiere confirmación para cambios)", icon: <ShieldAlert size={14} color="#f59e0b" /> },
  { cmd: "/mode plan", label: "/mode plan", desc: "Modo Planificador (solo análisis, sin modificar archivos)", icon: <Shield size={14} color="#3b82f6" /> },
  { cmd: "/mode review", label: "/mode review", desc: "Modo Auditoría AST y Code Review riguroso", icon: <Layers size={14} color="#a855f7" /> },
  { cmd: "/skills", label: "/skills", desc: "Ver catálogo de habilidades descubiertas (SKILL.md)", icon: <Layers size={14} color="#00d2ff" /> },
  { cmd: "/subagents", label: "/subagents", desc: "Ver estado y buzón de subagentes activos", icon: <Bot size={14} color="#10b981" /> },
  { cmd: "/artifacts", label: "/artifacts", desc: "Ver artefactos persistentes generados en la sesión", icon: <Package size={14} color="#f59e0b" /> },
  { cmd: "/language es", label: "/language es", desc: "Cambiar prompts del sistema al Español", icon: <Globe size={14} color="#00d2ff" /> },
  { cmd: "/language en", label: "/language en", desc: "Switch system prompts to English", icon: <Globe size={14} color="#00d2ff" /> },
  { cmd: "/cancel", label: "/cancel", desc: "Cancelar tarea activa del agente inmediatamente", icon: <Square size={14} color="#ef4444" /> },
  { cmd: "/test", label: "/test", desc: "Ejecutar suite completa de tests automatizados (pytest)", icon: <Play size={14} color="#00d2ff" /> },
  { cmd: "/diff", label: "/diff", desc: "Ver cambios pendientes de Git y abrir pestaña diff", icon: <GitBranch size={14} color="#a855f7" /> },
  { cmd: "/review", label: "/review", desc: "Auditoría de código AST sobre el archivo activo", icon: <FileCode size={14} color="#10b981" /> },
  { cmd: "/checkpoint", label: "/checkpoint [desc]", desc: "Crear snapshot de seguridad del espacio de trabajo", icon: <Save size={14} color="#3b82f6" /> },
  { cmd: "/undo", label: "/undo", desc: "Revertir al último checkpoint del agente sin tocar Git", icon: <RotateCcw size={14} color="#ef4444" /> },
  { cmd: "/vram", label: "/vram", desc: "Consultar uso de memoria VRAM GPU RTX 4060 en Ollama", icon: <Cpu size={14} color="#76b900" /> },
  { cmd: "/clear", label: "/clear", desc: "Limpiar la conversación en pantalla", icon: <Trash2 size={14} color="#8b949e" /> },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<"editor" | "diff">("editor");
  const [sidebarTab, setSidebarTab] = useState<"files" | "repomap" | "artifacts">("files");
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [selectedFile, setSelectedFile] = useState<string>("main.py");
  const [fileContent, setFileContent] = useState<string>("# Cargando código...");
  const [originalContent, setOriginalContent] = useState<string>("");
  const [fileList, setFileList] = useState<string[]>([]);
  const [fileFilter, setFileFilter] = useState<string>("");
  const [repoMap, setRepoMap] = useState<string>("");
  const [artifactsList, setArtifactsList] = useState<ArtifactItem[]>([]);
  const [vramInfo, setVramInfo] = useState<string>("Conectando con GPU...");
  const [agentMode, setAgentMode] = useState<string>("agent");
  const [language, setLanguage] = useState<string>("es");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "👋 ¡Hola! Soy **AETHER IDE** (Tauri v2 Desktop). Estoy conectado al Agent Runtime local con tu RTX 4060.\n\n💡 *Tip: Escribe `/` para ver comandos (`/test`, `/diff`, `/mode`, `/skills`, `/subagents`, `/artifacts`, etc.) o `@` para mencionar un archivo.*",
    },
  ]);
  const [inputPrompt, setInputPrompt] = useState<string>("");
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [gitDiff, setGitDiff] = useState<string>("");

  // Preguntas Interactivas del Agente (ask_question)
  const [pendingQuestions, setPendingQuestions] = useState<QuestionItem[] | null>(null);
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, string[]>>({});
  const [isSubmittingAnswer, setIsSubmittingAnswer] = useState<boolean>(false);

  // Slash commands popup state
  const [showSlashMenu, setShowSlashMenu] = useState<boolean>(false);
  const [slashIndex, setSlashIndex] = useState<number>(0);
  const [slashFilter, setSlashFilter] = useState<string>("");

  // File mention (@) popup state
  const [showMentionMenu, setShowMentionMenu] = useState<boolean>(false);
  const [mentionIndex, setMentionIndex] = useState<number>(0);
  const [mentionFilter, setMentionFilter] = useState<string>("");

  const inputRef = useRef<HTMLInputElement>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchStatus();
    fetchTree();
    fetchDiff();
    fetchArtifacts();
    loadFile("main.py");
  }, []);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isRunning, pendingQuestions]);

  // Polling automático de preguntas interactivas pendientes cuando el agente está pensando
  useEffect(() => {
    if (!isRunning) {
      setPendingQuestions(null);
      return;
    }
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${BRIDGE_URL}/api/question/pending`);
        if (res.ok) {
          const data = await res.json();
          if (data.pending && Array.isArray(data.questions) && data.questions.length > 0) {
            setPendingQuestions(data.questions);
            setSelectedAnswers((prev) => {
              const updated = { ...prev };
              data.questions.forEach((q: QuestionItem, i: number) => {
                if (!updated[i] || updated[i].length === 0) {
                  updated[i] = [q.options[0] || "Sí"];
                }
              });
              return updated;
            });
          } else {
            setPendingQuestions(null);
          }
        }
      } catch {}
    }, 1000);

    return () => clearInterval(interval);
  }, [isRunning]);

  // Global Keyboard Shortcuts (Ctrl+S, Escape, Ctrl+B)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveFile();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setSidebarCollapsed((prev) => !prev);
      } else if (e.key === "Escape") {
        if (showSlashMenu || showMentionMenu) {
          setShowSlashMenu(false);
          setShowMentionMenu(false);
        } else if (isRunning) {
          handleCancel();
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showSlashMenu, showMentionMenu, isRunning, fileContent, selectedFile]);

  async function fetchStatus() {
    try {
      const res = await fetch(`${BRIDGE_URL}/api/status`);
      if (res.ok) {
        const data = await res.json();
        setVramInfo(data.vram_info || "RTX 4060 · Online");
        if (data.mode) setAgentMode(data.mode);
        if (data.language) setLanguage(data.language);
      }
    } catch {
      setVramInfo("Bridge desconectado (Inicia bridge/server.py)");
    }
  }

  async function fetchTree() {
    try {
      const res = await fetch(`${BRIDGE_URL}/api/tree`);
      if (res.ok) {
        const data = await res.json();
        setRepoMap(data.repo_map || "");
        if (Array.isArray(data.files)) {
          setFileList(data.files);
        }
      }
    } catch {}
  }

  async function fetchDiff() {
    try {
      const res = await fetch(`${BRIDGE_URL}/api/diff`);
      if (res.ok) {
        const data = await res.json();
        setGitDiff(data.diff || "# No hay cambios pendientes de commit.");
      }
    } catch {}
  }

  async function fetchArtifacts() {
    try {
      const res = await fetch(`${BRIDGE_URL}/api/artifacts`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.artifacts)) {
          setArtifactsList(data.artifacts);
        }
      }
    } catch {}
  }

  async function loadArtifact(art: any) {
    const artId = art.id || art.artifact_id;
    if (!artId || artId === "undefined") return;
    try {
      const res = await fetch(`${BRIDGE_URL}/api/artifact?id=${encodeURIComponent(artId)}`);
      if (res.ok) {
        const data = await res.json();
        const displayName = `[Artefacto] ${art.title || artId}.md`;
        setSelectedFile(displayName);
        setFileContent(data.content || `# ${art.title || artId}\n${art.summary || ""}`);
        setOriginalContent(data.content || "");
        setActiveTab("editor");
      }
    } catch (err) {
      alert(`❌ Error cargando artefacto: ${err}`);
    }
  }

  async function loadFile(path: string) {
    try {
      const res = await fetch(`${BRIDGE_URL}/api/file?path=${encodeURIComponent(path)}`);
      if (res.ok) {
        const data = await res.json();
        const resolvedPath = data.path || path;
        setSelectedFile(resolvedPath);
        setFileContent(data.content);
        setOriginalContent(data.content);
        setActiveTab("editor");
      } else {
        const err = await res.json();
        alert(`❌ Error al abrir '${path}': ${err.error || "No encontrado"}`);
      }
    } catch (err) {
      alert(`❌ Error de red cargando archivo: ${err}`);
    }
  }

  async function saveFile() {
    if (fileContent === "# Cargando código..." || fileContent.trim() === "") {
      const proceed = confirm(
        `⚠️ El contenido de '${selectedFile}' parece estar vacío o aún cargando. ¿Estás seguro de que deseas guardar y sobrescribir el archivo en disco?`
      );
      if (!proceed) return;
    }

    try {
      const res = await fetch(`${BRIDGE_URL}/api/file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: selectedFile, content: fileContent }),
      });
      if (res.ok) {
        const data = await res.json();
        setOriginalContent(fileContent);
        fetchDiff();
        fetchTree();
        alert(`✅ Archivo '${data.path || selectedFile}' guardado en disco con éxito.`);
      } else {
        const err = await res.json();
        alert(`❌ Error guardando: ${err.error || "Fallo en servidor"}`);
      }
    } catch (err) {
      alert(`❌ Error guardando: ${err}`);
    }
  }

  function handleOptionToggle(qIdx: number, opt: string, isMulti?: boolean) {
    setSelectedAnswers((prev) => {
      const current = prev[qIdx] || [];
      if (isMulti) {
        const next = current.includes(opt)
          ? current.filter((x) => x !== opt)
          : [...current, opt];
        return { ...prev, [qIdx]: next.length > 0 ? next : [opt] };
      } else {
        return { ...prev, [qIdx]: [opt] };
      }
    });
  }

  async function handleSubmitAnswers() {
    if (!pendingQuestions || pendingQuestions.length === 0) return;
    setIsSubmittingAnswer(true);
    try {
      const answersPayload = pendingQuestions.map((q, idx) => ({
        question: q.question,
        selected: selectedAnswers[idx] && selectedAnswers[idx].length > 0 ? selectedAnswers[idx] : [q.options[0] || "Sí"],
      }));
      const res = await fetch(`${BRIDGE_URL}/api/question/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers: answersPayload }),
      });
      if (res.ok) {
        setPendingQuestions(null);
        setSelectedAnswers({});
      }
    } catch (err) {
      alert(`❌ Error enviando respuesta: ${err}`);
    } finally {
      setIsSubmittingAnswer(false);
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setInputPrompt(val);

    // Detectar si inicia con / para slash commands
    if (val.startsWith("/")) {
      const query = val.slice(1).toLowerCase();
      setSlashFilter(query);
      setShowSlashMenu(true);
      setShowMentionMenu(false);
      setSlashIndex(0);
    } else {
      setShowSlashMenu(false);
    }

    // Detectar si contiene @ para menciones de archivo
    const lastWord = val.split(" ").pop() || "";
    if (lastWord.startsWith("@")) {
      const query = lastWord.slice(1).toLowerCase();
      setMentionFilter(query);
      setShowMentionMenu(true);
      setShowSlashMenu(false);
      setMentionIndex(0);
    } else if (!val.startsWith("/")) {
      setShowMentionMenu(false);
    }
  }

  const filteredSlash = SLASH_COMMANDS.filter(
    (c) =>
      c.cmd.toLowerCase().includes(slashFilter) ||
      c.desc.toLowerCase().includes(slashFilter)
  );

  const filteredMentions = fileList.filter((f) =>
    f.toLowerCase().includes(mentionFilter)
  ).slice(0, 8);

  function applySlashCommand(cmd: string) {
    if (cmd === "/clear") {
      setMessages([]);
      setInputPrompt("");
      setShowSlashMenu(false);
      return;
    }
    setInputPrompt(cmd);
    setShowSlashMenu(false);
    inputRef.current?.focus();
  }

  function applyMention(filename: string) {
    const words = inputPrompt.split(" ");
    words.pop();
    words.push(`@${filename} `);
    setInputPrompt(words.join(" "));
    setShowMentionMenu(false);
    inputRef.current?.focus();
  }

  function handleInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (showSlashMenu && filteredSlash.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSlashIndex((prev) => (prev + 1) % filteredSlash.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSlashIndex((prev) => (prev - 1 + filteredSlash.length) % filteredSlash.length);
        return;
      }
      if (e.key === "Tab" || e.key === "Enter") {
        if (!e.shiftKey) {
          e.preventDefault();
          applySlashCommand(filteredSlash[slashIndex].cmd);
          return;
        }
      }
    }

    if (showMentionMenu && filteredMentions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex((prev) => (prev + 1) % filteredMentions.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex((prev) => (prev - 1 + filteredMentions.length) % filteredMentions.length);
        return;
      }
      if (e.key === "Tab" || e.key === "Enter") {
        if (!e.shiftKey) {
          e.preventDefault();
          applyMention(filteredMentions[mentionIndex]);
          return;
        }
      }
    }

    if (e.key === "Enter" && !e.shiftKey && !showSlashMenu && !showMentionMenu) {
      e.preventDefault();
      handleSendPrompt();
    }
  }

  async function handleSendPrompt(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!inputPrompt.trim() || isRunning) return;

    const userMsg = inputPrompt.trim();
    setInputPrompt("");
    setShowSlashMenu(false);
    setShowMentionMenu(false);

    // Si es comando /clear
    if (userMsg === "/clear") {
      setMessages([]);
      return;
    }

    const isCmd = userMsg.startsWith("/");
    setMessages((prev) => [...prev, { role: "user", content: userMsg, isCommand: isCmd }]);
    setIsRunning(true);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await fetch(`${BRIDGE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: userMsg, active_file: selectedFile }),
        signal: controller.signal,
      });

      if (res.ok) {
        const data = await res.json();
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.answer || "Tarea completada.", isCommand: data.is_command },
        ]);

        if (data.mode) setAgentMode(data.mode);
        if (data.language) setLanguage(data.language);

        if (data.action === "open_diff") {
          fetchDiff();
          setActiveTab("diff");
        } else if (data.action === "reload_file") {
          loadFile(selectedFile);
        }

        fetchDiff();
        fetchTree();
        fetchArtifacts();
      } else {
        const err = await res.json();
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `❌ Error: ${err.error || "Fallo en ejecución."}` },
        ]);
      }
    } catch (err: any) {
      if (err.name === "AbortError") {
        return;
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `❌ No se pudo contactar con el puente local: ${err}. Asegúrate de que 'bridge/server.py' esté corriendo.`,
        },
      ]);
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
        setIsRunning(false);
      }
    }
  }

  async function handleCancel() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    try {
      await fetch(`${BRIDGE_URL}/api/cancel`, { method: "POST" });
    } catch {}
    setIsRunning(false);
    setPendingQuestions(null);
  }

  async function cycleMode() {
    const modes = ["agent", "ask", "plan", "review"];
    const currentIdx = modes.indexOf(agentMode);
    const nextMode = modes[(currentIdx + 1) % modes.length];
    try {
      const res = await fetch(`${BRIDGE_URL}/api/mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: nextMode }),
      });
      if (res.ok) {
        const data = await res.json();
        setAgentMode(data.mode);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `🛡️ Modo cambiado a **${data.mode.toUpperCase()}**.`, isCommand: true },
        ]);
      }
    } catch {}
  }

  async function toggleLanguage() {
    const nextLang = language === "es" ? "en" : "es";
    try {
      const res = await fetch(`${BRIDGE_URL}/api/language`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language: nextLang }),
      });
      if (res.ok) {
        setLanguage(nextLang);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `🌐 Idioma del sistema actualizado a **${nextLang.toUpperCase()}**.`, isCommand: true },
        ]);
      }
    } catch {}
  }

  function getLanguage(filename: string): string {
    const ext = filename.split(".").pop()?.toLowerCase();
    switch (ext) {
      case "py": return "python";
      case "ts":
      case "tsx": return "typescript";
      case "js":
      case "jsx": return "javascript";
      case "json": return "json";
      case "md": return "markdown";
      case "css": return "css";
      case "html": return "html";
      case "bat": return "bat";
      case "sh": return "shell";
      case "yml":
      case "yaml": return "yaml";
      case "ini":
      case "toml": return "ini";
      default: return "plaintext";
    }
  }

  function getFileIcon(filename: string) {
    const ext = filename.split(".").pop()?.toLowerCase();
    if (ext === "py") return <Code2 size={13} color="#3b82f6" />;
    if (ext === "ts" || ext === "tsx") return <Code2 size={13} color="#00d2ff" />;
    if (ext === "md") return <FileText size={13} color="#10b981" />;
    if (ext === "json") return <FileCode size={13} color="#f59e0b" />;
    if (ext === "bat" || ext === "sh") return <Terminal size={13} color="#a855f7" />;
    return <FileCode size={13} color="#8b949e" />;
  }

  const filteredFiles = fileList.filter((f) =>
    f.toLowerCase().includes(fileFilter.toLowerCase())
  );

  const isDirty = fileContent !== originalContent;

  return (
    <div className="aether-ide-root">
      {/* Top Navigation Bar */}
      <header className="aether-header">
        <div className="brand">
          <button
            className="btn-icon"
            onClick={() => setSidebarCollapsed((p) => !p)}
            title="Colapsar / Expandir Barra Lateral (Ctrl+B)"
          >
            <Columns size={16} />
          </button>
          <Sparkles className="icon-sparkle" size={20} />
          <span className="brand-title">AETHER IDE</span>
          <span className="badge-tauri">Tauri v2 · Desktop</span>
        </div>
        <div className="status-badges">
          {/* Mode Switcher Pill */}
          <button
            className={`badge-mode ${agentMode}`}
            onClick={cycleMode}
            title="Clic para cambiar modo (Agent / Ask / Plan / Review)"
          >
            {agentMode === "agent" && <ShieldCheck size={13} />}
            {agentMode === "ask" && <ShieldAlert size={13} />}
            {agentMode === "plan" && <Shield size={13} />}
            {agentMode === "review" && <Layers size={13} />}
            <span>MODO: {agentMode.toUpperCase()}</span>
          </button>

          {/* Language Switcher Pill */}
          <button
            className="badge-lang"
            onClick={toggleLanguage}
            title="Clic para alternar idioma de prompts (ES / EN)"
          >
            <Globe size={13} />
            <span>{language.toUpperCase()}</span>
          </button>

          <div className="badge" title="VRAM Hardware Guard">
            <Cpu size={14} />
            <span>{vramInfo}</span>
          </div>
          <div className="badge">
            <GitBranch size={14} />
            <span>main</span>
          </div>
          <button
            className={`btn-save ${isDirty ? "dirty" : ""}`}
            onClick={saveFile}
            title={isDirty ? "Guardar cambios pendientes (Ctrl+S)" : "Sin cambios pendientes"}
          >
            <Save size={14} /> {isDirty ? "Guardar *" : "Guardado"}
          </button>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <div className="aether-workspace">
        {/* Left Sidebar: File Explorer / AST Repo-Map / Artifacts */}
        {!sidebarCollapsed && (
          <aside className="aether-sidebar">
            <div className="sidebar-tab-header">
              <button
                className={`sidebar-tab-btn ${sidebarTab === "files" ? "active" : ""}`}
                onClick={() => setSidebarTab("files")}
              >
                <FolderTree size={14} /> Archivos ({fileList.length})
              </button>
              <button
                className={`sidebar-tab-btn ${sidebarTab === "repomap" ? "active" : ""}`}
                onClick={() => setSidebarTab("repomap")}
              >
                <Sparkles size={14} /> Mapa IA
              </button>
              <button
                className={`sidebar-tab-btn ${sidebarTab === "artifacts" ? "active" : ""}`}
                onClick={() => {
                  fetchArtifacts();
                  setSidebarTab("artifacts");
                }}
              >
                <Package size={14} /> Artefactos ({artifactsList.length})
              </button>
              <button
                className="btn-icon"
                onClick={() => {
                  fetchTree();
                  fetchArtifacts();
                }}
                title="Actualizar explorador"
              >
                <RefreshCw size={12} />
              </button>
            </div>

            {sidebarTab === "files" ? (
              <div className="file-explorer-container">
                <div className="file-search-bar">
                  <Search size={13} className="search-icon" />
                  <input
                    type="text"
                    placeholder="Buscar archivo..."
                    value={fileFilter}
                    onChange={(e) => setFileFilter(e.target.value)}
                  />
                </div>
                <div className="file-list">
                  {filteredFiles.map((f) => (
                    <div
                      key={f}
                      className={`file-item ${selectedFile === f ? "selected" : ""}`}
                      onClick={() => loadFile(f)}
                      title={f}
                    >
                      {getFileIcon(f)}
                      <span className="file-name">{f}</span>
                    </div>
                  ))}
                  {filteredFiles.length === 0 && (
                    <div className="file-empty">No se encontraron archivos coincidentes.</div>
                  )}
                </div>
              </div>
            ) : sidebarTab === "repomap" ? (
              <pre className="repo-map-view">{repoMap || "Cargando mapa arquitectónico AST..."}</pre>
            ) : (
              <div className="artifact-list">
                {artifactsList.map((art: any) => {
                  const artId = art.id || art.artifact_id || "art";
                  return (
                    <div
                      key={artId}
                      className="artifact-card"
                      onClick={() => loadArtifact(art)}
                      title={`Artefacto: ${art.title || artId} (${art.type || 'doc'})`}
                    >
                      <div className="artifact-title">{art.title || artId}</div>
                      <div className="artifact-meta">
                        <span>🏷️ {art.type || 'documento'}</span>
                        <span>📅 {art.created_at ? new Date(art.created_at).toLocaleTimeString() : ''}</span>
                      </div>
                    </div>
                  );
                })}
                {artifactsList.length === 0 && (
                  <div className="file-empty">No hay artefactos en esta sesión aún.</div>
                )}
              </div>
            )}
          </aside>
        )}

        {/* Center: Monaco Code Editor / Diff Editor */}
        <main className="aether-editor-stage">
          <div className="editor-tabs">
            <button
              className={`tab ${activeTab === "editor" ? "active" : ""}`}
              onClick={() => setActiveTab("editor")}
            >
              <FileCode size={14} /> {selectedFile} {isDirty && "*"}
            </button>
            <button
              className={`tab ${activeTab === "diff" ? "active" : ""}`}
              onClick={() => {
                fetchDiff();
                setActiveTab("diff");
              }}
            >
              <GitBranch size={14} /> Git Diff
            </button>
            <button
              className="btn-icon"
              style={{ marginLeft: "auto", marginRight: "10px" }}
              title="Recargar archivo desde el disco"
              onClick={() => loadFile(selectedFile)}
            >
              <RotateCcw size={13} />
            </button>
          </div>

          <div className="editor-container">
            {activeTab === "editor" ? (
              <Editor
                height="100%"
                theme="vs-dark"
                path={selectedFile}
                language={getLanguage(selectedFile)}
                value={fileContent}
                onChange={(val) => setFileContent(val || "")}
                options={{
                  minimap: { enabled: true },
                  fontSize: 14,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                }}
              />
            ) : (
              <DiffEditor
                height="100%"
                theme="vs-dark"
                original={originalContent}
                modified={gitDiff}
                language={getLanguage(selectedFile)}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  automaticLayout: true,
                }}
              />
            )}
          </div>
        </main>

        {/* Right Sidebar: AETHER Autonomous Agent Panel */}
        <section className="aether-agent-panel">
          <div className="panel-header">
            <div className="panel-title">
              <Sparkles size={16} />
              <span>Agente Autónomo</span>
            </div>
            {isRunning ? (
              <button className="btn-cancel" onClick={handleCancel} title="Cancelar tarea activa (Escape)">
                <Square size={12} /> Detener (Esc)
              </button>
            ) : (
              <span className="agent-status-idle">IDLE</span>
            )}
          </div>

          <div className="chat-messages">
            {messages.map((m, idx) => (
              <div key={idx} className={`chat-bubble ${m.role} ${m.isCommand ? "command-bubble" : ""}`}>
                <div className="role-label">{m.role.toUpperCase()}</div>
                <div className="bubble-content">{m.content}</div>
              </div>
            ))}

            {/* Tarjeta de Pregunta Interactiva (ask_question) */}
            {pendingQuestions && pendingQuestions.length > 0 && (
              <div className="interactive-question-card">
                <div className="question-header">
                  <HelpCircle size={16} className="question-icon" />
                  <span className="question-badge">PREGUNTA INTERACTIVA</span>
                </div>
                {pendingQuestions.map((q, qIdx) => (
                  <div key={qIdx} className="question-item">
                    <p className="question-text">{q.question}</p>
                    <div className="options-container">
                      {q.options.map((opt, oIdx) => {
                        const isSelected = (selectedAnswers[qIdx] || []).includes(opt);
                        return (
                          <button
                            key={oIdx}
                            type="button"
                            className={`option-btn ${isSelected ? "selected" : ""}`}
                            onClick={() => handleOptionToggle(qIdx, opt, q.is_multi_select)}
                          >
                            <span className="option-indicator">{isSelected ? "●" : "○"}</span>
                            <span className="option-label">{opt}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
                <div className="question-actions">
                  <button
                    type="button"
                    className="btn-submit-answer"
                    onClick={handleSubmitAnswers}
                    disabled={isSubmittingAnswer}
                  >
                    {isSubmittingAnswer ? (
                      <RefreshCw size={14} className="spin" />
                    ) : (
                      <Send size={14} />
                    )}
                    <span>Responder al Agente</span>
                  </button>
                </div>
              </div>
            )}

            {isRunning && (
              <div className="chat-bubble assistant thinking">
                <RefreshCw size={14} className="spin" />
                <span>AETHER pensando y ejecutando herramientas...</span>
              </div>
            )}
            <div ref={chatBottomRef} />
          </div>

          {/* Floating Slash Commands Popup */}
          {showSlashMenu && filteredSlash.length > 0 && (
            <div className="slash-command-popup">
              <div className="popup-header">Comandos Disponibles (↑ ↓ para navegar, Tab/Enter para seleccionar)</div>
              <div className="popup-list">
                {filteredSlash.map((c, i) => (
                  <div
                    key={c.cmd}
                    className={`popup-item ${i === slashIndex ? "active" : ""}`}
                    onClick={() => applySlashCommand(c.cmd)}
                  >
                    <div className="item-icon">{c.icon}</div>
                    <div className="item-info">
                      <div className="item-title">{c.label}</div>
                      <div className="item-desc">{c.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Floating File Mention Popup */}
          {showMentionMenu && filteredMentions.length > 0 && (
            <div className="slash-command-popup mention-popup">
              <div className="popup-header">Mencionar Archivo del Proyecto (@)</div>
              <div className="popup-list">
                {filteredMentions.map((f, i) => (
                  <div
                    key={f}
                    className={`popup-item ${i === mentionIndex ? "active" : ""}`}
                    onClick={() => applyMention(f)}
                  >
                    <div className="item-icon">{getFileIcon(f)}</div>
                    <div className="item-info">
                      <div className="item-title">{f}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <form className="chat-input-bar" onSubmit={handleSendPrompt}>
            <input
              ref={inputRef}
              type="text"
              placeholder="Pregunta o ejecuta comandos con / (/test, /diff, /skills, /artifacts)..."
              value={inputPrompt}
              disabled={isRunning}
              onChange={handleInputChange}
              onKeyDown={handleInputKeyDown}
            />
            <button type="submit" disabled={isRunning || !inputPrompt.trim()} title="Enviar (Enter)">
              <Play size={16} />
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
