import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import { useTheme } from "../../theme/ThemeProvider";

if (typeof window !== "undefined") {
  window.MonacoEnvironment = {
    getWorker: () => new editorWorker(),
  };
  loader.config({ monaco });
}

function languageForPath(path: string): string {
  const name = path.toLowerCase();
  if (name.endsWith(".py")) return "python";
  if (name.endsWith(".yaml") || name.endsWith(".yml")) return "yaml";
  if (name.endsWith(".json")) return "json";
  if (name.endsWith(".md")) return "markdown";
  if (name.endsWith(".sh") || name.endsWith(".bash")) return "shell";
  if (name.endsWith(".ts") || name.endsWith(".tsx")) return "typescript";
  if (name.endsWith(".js") || name.endsWith(".mjs") || name.endsWith(".cjs")) return "javascript";
  if (name.endsWith(".go")) return "go";
  if (name.endsWith(".toml") || name.endsWith(".ini")) return "ini";
  if (name.endsWith(".html") || name.endsWith(".htm")) return "html";
  if (name.endsWith(".css")) return "css";
  return "plaintext";
}

type ScriptCodeEditorProps = {
  path: string;
  value: string;
  onChange: (next: string) => void;
  readOnly?: boolean;
  onSave?: () => void;
};

export function ScriptCodeEditor({ path, value, onChange, readOnly, onSave }: ScriptCodeEditorProps) {
  const { isDark } = useTheme();

  return (
    <Editor
      className="alfred-scripts-monaco-inner"
      height="100%"
      path={path}
      language={languageForPath(path)}
      theme={isDark ? "vs-dark" : "vs"}
      value={value}
      onChange={(next) => onChange(next ?? "")}
      loading={<div className="alfred-scripts-monaco-loading">Loading editor…</div>}
      options={{
        readOnly,
        minimap: { enabled: true, scale: 1 },
        fontSize: 13,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        lineNumbers: "on",
        wordWrap: "on",
        automaticLayout: true,
        scrollBeyondLastLine: false,
        tabSize: path.toLowerCase().endsWith(".py") ? 4 : 2,
        renderWhitespace: "selection",
        padding: { top: 12, bottom: 12 },
        smoothScrolling: true,
        cursorBlinking: "smooth",
        matchBrackets: "always",
        folding: true,
        glyphMargin: false,
        fixedOverflowWidgets: true,
      }}
      onMount={(editor) => {
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
          onSave?.();
        });
      }}
    />
  );
}
