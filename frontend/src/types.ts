export type AppView = "home" | "chat" | "settings";
export type SettingsPage =
  | "branding"
  | "ai"
  | "secrets"
  | "integrations"
  | "knowledge"
  | "repos"
  | "playbooks"
  | "scripts"
  | "tools"
  | "routing"
  | "health"
  | "usage"
  | "schedules"
  | "logs";

export type GitRepoProfile = {
  repo: string;
  role: "code" | "docs" | "scripts";
  doc_index?: boolean | null;
  graphify?: boolean | null;
};

export const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama",
  openai: "OpenAI",
  anthropic: "Claude",
  gemini: "Gemini",
  kimi: "Kimi",
};
