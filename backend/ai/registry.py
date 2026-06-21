"""Build LLM providers from config and route by task type."""

from __future__ import annotations

from backend.ai.anthropic_adapter import AnthropicProvider
from backend.ai.base import LLMProvider
from backend.ai.gemini_adapter import GeminiProvider
from backend.ai.openai_compat import OpenAICompatProvider
from backend.models.config import AIConfig, AIProviderConfig, AlfredConfig


OPENAI_COMPAT_NAMES = {"ollama", "openai", "groq", "together", "mistral", "kimi"}


def build_provider(name: str, config: AIProviderConfig) -> LLMProvider:
    if name == "anthropic":
        return AnthropicProvider(config)
    if name == "gemini":
        return GeminiProvider(config)
    return OpenAICompatProvider(name, config)


class LLMRouter:
    def __init__(self, ai_config: AIConfig) -> None:
        self.ai_config = ai_config
        self._providers: dict[str, LLMProvider] = {}

    @classmethod
    def from_config(cls, config: AlfredConfig) -> "LLMRouter":
        return cls(config.ai)

    def get(self, provider_name: str | None = None) -> LLMProvider:
        name = provider_name or self.ai_config.default_provider
        if name not in self._providers:
            provider_cfg = self.ai_config.providers.get(name)
            if provider_cfg is None:
                raise KeyError(f"Unknown AI provider: {name}")
            self._providers[name] = build_provider(name, provider_cfg)
        return self._providers[name]

    def for_task(self, task_type: str) -> LLMProvider:
        routing = self.ai_config.routing
        provider_name = getattr(routing, task_type, None) or self.ai_config.default_provider
        return self.get(provider_name)

    def list_providers(self) -> list[dict]:
        result = []
        for name, cfg in self.ai_config.providers.items():
            try:
                provider = self.get(name)
                available = provider.is_available()
            except Exception:
                available = False
            result.append(
                {
                    "name": name,
                    "enabled": cfg.enabled,
                    "model": cfg.model,
                    "base_url": cfg.base_url,
                    "available": available,
                    "adapter": "anthropic"
                    if name == "anthropic"
                    else "gemini"
                    if name == "gemini"
                    else "openai_compat",
                }
            )
        return result

    def ping(self, provider_name: str | None = None) -> dict:
        name = provider_name or self.ai_config.default_provider
        provider = self.get(name)
        from backend.ai.base import Message

        try:
            response = provider.chat(
                [Message(role="user", content="Reply with exactly: pong")],
                model=self.ai_config.providers[name].model,
            )
            reply = (response.content or "").strip()
            return {
                "provider": name,
                "model": response.model,
                "reply": reply,
                "ok": bool(reply),
                "message": reply or "Empty response from model",
            }
        except Exception as exc:
            msg = str(exc)
            if name == "ollama" and "not found" in msg.lower():
                msg = f"Model not pulled — run: alfred ollama pull --model {self.ai_config.providers[name].model}"
            return {"provider": name, "ok": False, "message": msg, "reply": ""}
