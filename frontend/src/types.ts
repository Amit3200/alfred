export type AppView = "home" | "chat" | "settings";
export type SettingsPage = "ai" | "secrets" | "integrations" | "health";

export const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama",
  openai: "OpenAI",
  anthropic: "Claude",
  gemini: "Gemini",
};
