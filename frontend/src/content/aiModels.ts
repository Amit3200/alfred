/** Known model IDs per provider — used for routing dropdowns; custom values still allowed. */
export const PROVIDER_MODELS: Record<string, string[]> = {
  ollama: ["llama3", "llama3.2:3b", "llama3.1:8b", "mistral", "qwen2.5-coder:7b"],
  openai: ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"],
  anthropic: [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-5-haiku-latest",
  ],
  gemini: ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro"],
  kimi: ["kimi-k2.6", "kimi-k2.5", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
};

export type LLMRouteKey =
  | "skill_matching"
  | "investigation"
  | "basic_chat"
  | "pr_review"
  | "workflow_execution";

export const ROUTE_LABELS: Record<LLMRouteKey, string> = {
  skill_matching: "Skill matching",
  investigation: "Investigation",
  basic_chat: "Basic chat",
  pr_review: "PR review",
  workflow_execution: "Workflow execution",
};

export const ROUTE_DESCRIPTIONS: Record<LLMRouteKey, string> = {
  skill_matching: "Pick the right skill/playbook when keyword triggers miss.",
  investigation: "Tool-calling agent loops — AWS, git, JIRA, etc.",
  basic_chat: "Simple Q&A without tools.",
  pr_review: "PR review skill and code analysis.",
  workflow_execution: "JIRA writes and future workflow actions.",
};

export function modelOptionsForProvider(
  providerName: string,
  providerDefaultModel?: string,
  currentModel?: string,
): { value: string; label: string }[] {
  const known = PROVIDER_MODELS[providerName] ?? [];
  const values = new Set<string>(known);
  if (providerDefaultModel) values.add(providerDefaultModel);
  if (currentModel) values.add(currentModel);

  const options = [
    { value: "", label: "Provider default" },
    ...Array.from(values).map((value) => ({
      value,
      label: value === providerDefaultModel ? `${value} (default)` : value,
    })),
  ];
  return options;
}
