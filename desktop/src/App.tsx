import React, { useState, useEffect } from "react";
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
} from "lucide-react";
import "./App.css";

const BRIDGE_URL = "http://127.0.0.1:8765";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<"editor" | "diff">("editor");
  const [sidebarTab, setSidebarTab] = useState<"files" | "repomap">("files");
  const [selectedFile, setSelectedFile] = useState<string>("main.py");
  const [fileContent, setFileContent] = useState<string>("# Cargando código...");
  const [originalContent, setOriginalContent] = useState<string>("");
  const [fileList, setFileList] = useState<string[]>([]);
  const [fileFilter, setFileFilter] = useState<string>("");
  const [repoMap, setRepoMap] = useState<string>("");
  const [vramInfo, setVramInfo] = useState<string>("Conectando con GPU...");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "👋 ¡Hola! Soy **AETHER IDE** (Tauri v2 Desktop). Estoy conectado al Agent Runtime local y listo para programar de forma autónoma con tu RTX 4060.",
    },
  ]);
  const [inputPrompt, setInputPrompt] = useState<string>("");
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [gitDiff, setGitDiff] = useState<string>("");

  useEffect(() => {
    fetchStatus();
    fetchTree();
    fetchDiff();
    loadFile("main.py");
  }, []);

  async function fetchStatus() {
    try {
      const res = await fetch(`${BRIDGE_URL}/api/status`);
      if (res.ok) {
        const data = await res.json();
        setVramInfo(data.vram_info || "RTX 4060 · Online");
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

  async function handleSendPrompt(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!inputPrompt.trim() || isRunning) return;

    const userMsg = inputPrompt.trim();
    setInputPrompt("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setIsRunning(true);

    try {
      const res = await fetch(`${BRIDGE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: userMsg }),
      });

      if (res.ok) {
        const data = await res.json();
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.answer || "Tarea completada." },
        ]);
        fetchDiff();
        fetchTree();
        loadFile(selectedFile);
      } else {
        const err = await res.json();
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `❌ Error: ${err.error || "Fallo en ejecución."}` },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `❌ No se pudo contactar con el puente local: ${err}. Asegúrate de ejecutar 'python bridge/server.py'.`,
        },
      ]);
    } finally {
      setIsRunning(false);
    }
  }

  async function handleCancel() {
    try {
      await fetch(`${BRIDGE_URL}/api/cancel`, { method: "POST" });
    } catch {}
    setIsRunning(false);
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
          <Sparkles className="icon-sparkle" size={20} />
          <span className="brand-title">AETHER IDE</span>
          <span className="badge-tauri">Tauri v2 · Desktop</span>
        </div>
        <div className="status-badges">
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
            title={isDirty ? "Guardar cambios pendientes (Ctrl+S)" : "Sin cambios"}
          >
            <Save size={14} /> {isDirty ? "Guardar *" : "Guardado"}
          </button>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <div className="aether-workspace">
        {/* Left Sidebar: File Explorer / AST Repo-Map */}
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
            <button className="btn-icon" onClick={fetchTree} title="Actualizar árbol y mapa">
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
          ) : (
            <pre className="repo-map-view">{repoMap || "Cargando mapa arquitectónico AST..."}</pre>
          )}
        </aside>

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
            <Sparkles size={16} />
            <span>Agente Autónomo</span>
            {isRunning ? (
              <button className="btn-cancel" onClick={handleCancel}>
                <Square size={12} /> Cancelar
              </button>
            ) : (
              <span className="agent-status-idle">IDLE</span>
            )}
          </div>

          <div className="chat-messages">
            {messages.map((m, idx) => (
              <div key={idx} className={`chat-bubble ${m.role}`}>
                <div className="role-label">{m.role.toUpperCase()}</div>
                <div className="bubble-content">{m.content}</div>
              </div>
            ))}
            {isRunning && (
              <div className="chat-bubble assistant thinking">
                <RefreshCw size={14} className="spin" />
                <span>AETHER pensando y ejecutando herramientas...</span>
              </div>
            )}
          </div>

          <form className="chat-input-bar" onSubmit={handleSendPrompt}>
            <input
              type="text"
              placeholder="Pídele a AETHER que implemente, corrija o pruebe algo..."
              value={inputPrompt}
              disabled={isRunning}
              onChange={(e) => setInputPrompt(e.target.value)}
            />
            <button type="submit" disabled={isRunning || !inputPrompt.trim()}>
              <Play size={16} />
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
