export type AppView = "home" | "chat" | "settings";
export type SettingsPage = "branding" | "ai" | "secrets" | "integrations" | "repos" | "playbooks" | "health" | "usage" | "schedules" | "logs";

export const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama",
  openai: "OpenAI",
  anthropic: "Claude",
  gemini: "Gemini",
  kimi: "Kimi",
};
