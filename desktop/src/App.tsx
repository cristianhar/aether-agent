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
} from "lucide-react";
import "./App.css";

const BRIDGE_URL = "http://127.0.0.1:8765";

interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<"editor" | "diff">("editor");
  const [selectedFile, setSelectedFile] = useState<string>("main.py");
  const [fileContent, setFileContent] = useState<string>("# Cargando código...");
  const [originalContent, setOriginalContent] = useState<string>("");
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

  // Cargar estado inicial y repo-map desde el puente local
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
        setSelectedFile(path);
        setFileContent(data.content);
        setOriginalContent(data.content);
      }
    } catch (err) {
      alert(`Error cargando archivo: ${err}`);
    }
  }

  async function saveFile() {
    try {
      const res = await fetch(`${BRIDGE_URL}/api/file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: selectedFile, content: fileContent }),
      });
      if (res.ok) {
        setOriginalContent(fileContent);
        fetchDiff();
        alert(`✅ Archivo '${selectedFile}' guardado con éxito.`);
      }
    } catch (err) {
      alert(`Error guardando: ${err}`);
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

  const quickFiles = ["main.py", "agent/orchestrator.py", "tools/registry.py", "README.md"];

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
          <button className="btn-save" onClick={saveFile} title="Guardar archivo">
            <Save size={14} /> Guardar
          </button>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <div className="aether-workspace">
        {/* Left Sidebar: Explorador de Archivos / Repo-Map */}
        <aside className="aether-sidebar">
          <div className="sidebar-header">
            <FolderTree size={16} />
            <span>Arquitectura (Repo-Map)</span>
            <button className="btn-icon" onClick={fetchTree} title="Actualizar mapa">
              <RefreshCw size={12} />
            </button>
          </div>
          <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border-color)", display: "flex", gap: "6px", flexWrap: "wrap" }}>
            {quickFiles.map((qf) => (
              <button
                key={qf}
                className="btn-icon"
                style={{ fontSize: "11px", padding: "2px 6px", background: selectedFile === qf ? "var(--bg-hover)" : "transparent", color: "var(--text-main)" }}
                onClick={() => loadFile(qf)}
              >
                {qf.split("/").pop()}
              </button>
            ))}
          </div>
          <pre className="repo-map-view">{repoMap || "Cargando mapa arquitectónico..."}</pre>
        </aside>

        {/* Center: Monaco Code Editor / Diff Editor */}
        <main className="aether-editor-stage">
          <div className="editor-tabs">
            <button
              className={`tab ${activeTab === "editor" ? "active" : ""}`}
              onClick={() => setActiveTab("editor")}
            >
              <FileCode size={14} /> {selectedFile}
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
              title="Recargar archivo del disco"
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
                defaultLanguage="python"
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
                language="python"
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
