import type { ReactNode } from "react";

export type HelpGuide = {
  title: string;
  summary: string;
  steps: string[];
  links?: { label: string; href: string }[];
};

export const SECRETS_HELP: Record<string, HelpGuide> = {
  slack: {
    title: "Slack",
    summary:
      "Alfred listens for @mentions in Slack via Socket Mode (no public URL needed). You need Bot Token, Signing Secret, and App-Level Token.",
    steps: [
      "Go to api.slack.com/apps → Create New App → From scratch.",
      "Basic Information → enable Socket Mode → create App-Level Token with connections:write (xapp-).",
      "OAuth & Permissions → Bot Token Scopes: app_mentions:read, channels:history, channels:read, chat:write, im:history, im:write, groups:history, groups:read, users:read, assistant:write (Agents & AI Apps).",
      "Enable Agents & AI Apps in app settings for native thinking status (no edited placeholder message).",
      "Event Subscriptions → Subscribe to bot events → add app_mention.",
      "Install to workspace → copy Bot User OAuth Token (xoxb-) and Signing Secret.",
      "Save all three tokens in Secrets, enable Slack in Integrations, then restart alfred serve.",
      "Invite the bot to a channel: /invite @Alfred — then @mention it to chat.",
    ],
    links: [{ label: "Slack API docs", href: "https://api.slack.com/start/quickstart" }],
  },
  git: {
    title: "Git",
    summary:
      "Personal access token lets Alfred read repos, blame, grep, open PRs, and post PR review comments.",
    steps: [
      "GitHub: Settings → Developer settings → Personal access tokens → Fine-grained or classic.",
      "Scopes: repo (read for investigation; write if Alfred posts PR comments on GitHub).",
      "GitLab: Preferences → Access Tokens → api, read_repository, write_repository as needed.",
      "Paste the token here — it is encrypted and never written to config.yaml.",
    ],
    links: [
      { label: "GitHub tokens", href: "https://github.com/settings/tokens" },
      { label: "GitLab tokens", href: "https://gitlab.com/-/user_settings/personal_access_tokens" },
    ],
  },
  github: {
    title: "GitHub App",
    summary:
      "Webhook secret and optional client secret for @alfred on pull request comments. Requires a public HTTPS URL (Cloudflare tunnel or similar).",
    steps: [
      "Create a GitHub App → set Webhook URL and Callback URL to your Alfred host (/api/v1/github/webhook and /callback).",
      "Generate a webhook secret on GitHub → paste the same value here as Webhook secret.",
      "Optional: paste Client secret from the GitHub App for OAuth callback.",
      "Enable GitHub App in Integrations, set client_id and callback_base_url, then save config.",
      "Install the app on your org/repos. Subscribe to Issue comment events.",
      "Verify: GitHub App → Webhook → Recent deliveries (ping should return 200).",
    ],
    links: [{ label: "GitHub Apps", href: "https://github.com/settings/apps" }],
  },
  aws: {
    title: "AWS",
    summary:
      "IAM credentials for read-only CloudWatch, ECS, and S3 queries. Use a scoped policy — not root keys.",
    steps: [
      "IAM → Users → Create user with programmatic access.",
      "Attach a custom policy limiting to: logs:FilterLogEvents, ecs:Describe*, s3:ListBucket, s3:GetObject.",
      "Copy Access Key ID and Secret Access Key.",
      "Alternatively, leave blank and use an AWS profile configured on the server (see Integrations tab).",
    ],
    links: [{ label: "IAM best practices", href: "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html" }],
  },
};

export const AI_KEY_HELP: Record<string, HelpGuide> = {
  openai: {
    title: "OpenAI",
    summary: "API key for GPT models. Also works with any OpenAI-compatible proxy if you change the base URL in AI settings.",
    steps: [
      "platform.openai.com → API keys → Create new secret key.",
      "Set billing limits if needed.",
      "Paste sk-... here. Configure model name on the AI providers page.",
    ],
    links: [{ label: "OpenAI API keys", href: "https://platform.openai.com/api-keys" }],
  },
  anthropic: {
    title: "Claude (Anthropic)",
    summary: "Native Claude API for investigation and workflow skills.",
    steps: [
      "console.anthropic.com → API Keys → Create Key.",
      "Paste the key here. Default model: claude-sonnet (configurable on AI page).",
    ],
    links: [{ label: "Anthropic console", href: "https://console.anthropic.com/" }],
  },
  gemini: {
    title: "Google Gemini",
    summary: "Google AI Studio API key for Gemini models.",
    steps: [
      "aistudio.google.com → Get API key → Create API key.",
      "Paste here. Set model (e.g. gemini-2.0-flash) on the AI providers page.",
    ],
    links: [{ label: "Google AI Studio", href: "https://aistudio.google.com/apikey" }],
  },
  kimi: {
    title: "Kimi (Moonshot AI)",
    summary: "API key from the Kimi Open Platform — OpenAI-compatible chat API.",
    steps: [
      "platform.kimi.ai → create an API key.",
      "Paste the key here. Default model: kimi-k2.6 (configurable on AI providers page).",
      "Use https://api.moonshot.cn/v1 as base URL if you are in mainland China.",
    ],
    links: [
      { label: "Kimi API platform", href: "https://platform.kimi.ai/docs/api/quickstart" },
      { label: "Kimi", href: "https://www.kimi.com/en" },
    ],
  },
};

export const AI_PROVIDER_HELP: Record<string, HelpGuide> = {
  ollama: {
    title: "Ollama (local)",
    summary: "Run models locally — no API key. Install Ollama and pull a model.",
    steps: [
      "Install from ollama.com and run: ollama pull llama3",
      "Default base URL: http://localhost:11434/v1",
      "Good for dev and cheap skill-matching. No secret required.",
    ],
    links: [{ label: "Ollama download", href: "https://ollama.com/download" }],
  },
  openai: {
    title: "OpenAI",
    summary: "GPT-4o, GPT-4o-mini, and compatible endpoints.",
    steps: [
      "Add API key in Secrets → AI keys.",
      "Set model name (e.g. gpt-4o-mini) below.",
      "Works with Groq, Together, etc. if you change Base URL.",
    ],
    links: [{ label: "Models", href: "https://platform.openai.com/docs/models" }],
  },
  anthropic: {
    title: "Claude",
    summary: "Anthropic Claude — strong for investigation and tool use.",
    steps: [
      "Add API key in Secrets → AI keys.",
      "Recommended for investigation routing.",
    ],
    links: [{ label: "Model overview", href: "https://docs.anthropic.com/en/docs/about-claude/models" }],
  },
  gemini: {
    title: "Gemini",
    summary: "Google Gemini — fast and cost-effective.",
    steps: [
      "Add API key in Secrets → AI keys.",
      "Set model to gemini-2.0-flash or similar.",
    ],
    links: [{ label: "Gemini models", href: "https://ai.google.dev/gemini-api/docs/models/gemini" }],
  },
  kimi: {
    title: "Kimi (Moonshot AI)",
    summary: "Kimi K2 models via the Moonshot Open Platform — strong for coding and agent tasks.",
    steps: [
      "Add API key in Secrets → AI keys.",
      "Default base URL: https://api.moonshot.ai/v1",
      "Default model: kimi-k2.6 — good for investigation routing.",
      "China region: set base URL to https://api.moonshot.cn/v1",
    ],
    links: [
      { label: "Kimi API docs", href: "https://platform.kimi.ai/docs/api/overview" },
      { label: "Kimi", href: "https://www.kimi.com/en" },
    ],
  },
};

export function renderHelpContent(guide: HelpGuide): ReactNode {
  return (
    <div className="alfred-help-popover">
      <p>{guide.summary}</p>
      <ol>
        {guide.steps.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>
      {guide.links?.map((link) => (
        <a key={link.href} href={link.href} target="_blank" rel="noreferrer">
          {link.label} ↗
        </a>
      ))}
    </div>
  );
}
