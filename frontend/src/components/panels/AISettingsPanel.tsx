import { AutoComplete, Button, Col, Input, Row, Select, Switch, Typography } from "antd";
import { useMemo } from "react";
import {
  LLMRouteKey,
  ROUTE_DESCRIPTIONS,
  ROUTE_LABELS,
  modelOptionsForProvider,
} from "../../content/aiModels";
import { AI_PROVIDER_HELP, renderHelpContent } from "../../content/helpText";
import { useApp } from "../../context/AppContext";
import { useSectionVisibility } from "../../hooks/useSectionVisibility";
import type { LLMRouteConfig } from "../../api/client";
import { PROVIDER_LABELS } from "../../types";
import {
  ActiveSections,
  AddableSection,
  AddableSectionList,
} from "../ui/AddableSection";
import { OllamaGetStarted } from "../OllamaGetStarted";

const ALL_PROVIDERS = ["ollama", "openai", "anthropic", "gemini", "kimi"] as const;

const ROUTE_KEYS: LLMRouteKey[] = [
  "skill_matching",
  "investigation",
  "basic_chat",
  "pr_review",
  "workflow_execution",
];

function normalizeRoute(route: LLMRouteConfig | string | undefined): LLMRouteConfig {
  if (!route) return { provider: "", model: "" };
  if (typeof route === "string") return { provider: route, model: "" };
  return route;
}

export function AISettingsPanel() {
  const { config, updateConfig, saveConfig, testProvider } = useApp();

  const configuredIds = useMemo(() => {
    if (!config) return [];
    return ALL_PROVIDERS.filter((name) => {
      const p = config.ai.providers[name];
      return p?.enabled || config.ai.default_provider === name;
    });
  }, [config]);

  const sections = useSectionVisibility("ai-providers");

  const allOptions = ALL_PROVIDERS.map((name) => ({
    value: name,
    label: PROVIDER_LABELS[name] || name,
  }));

  if (!config) {
    return (
      <Typography.Text type="secondary">Loading configuration…</Typography.Text>
    );
  }

  const configured = config._secrets_configured;

  const updateRoute = (key: LLMRouteKey, patch: Partial<LLMRouteConfig>) => {
    const current = normalizeRoute(config.ai.routing[key]);
    updateConfig({
      ai: {
        ...config.ai,
        routing: {
          ...config.ai.routing,
          [key]: { ...current, ...patch },
        },
      },
    });
  };

  return (
    <div className="alfred-settings-page">
      <Typography.Title level={3} className="alfred-page-title">
        AI providers
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Add providers you want to use. Set routing below — pick a provider and optional model per
        purpose. Leave model empty to use each provider&apos;s default.
      </Typography.Paragraph>

      {sections.isVisible("ollama") && (
        <div style={{ marginBottom: 20 }}>
          <OllamaGetStarted compact />
        </div>
      )}

      <div className="alfred-panel" style={{ marginBottom: 20 }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8}>
            <label className="alfred-field-label">Default provider</label>
            <Select
              style={{ width: "100%" }}
              value={config.ai.default_provider}
              options={allOptions}
              getPopupContainer={(n) => n.parentElement ?? document.body}
              onChange={(v) => updateConfig({ ai: { ...config.ai, default_provider: v } })}
            />
          </Col>
        </Row>

        <Typography.Title level={5} style={{ marginTop: 20, marginBottom: 4 }}>
          Task routing
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 16, fontSize: 13 }}>
          Choose which provider and model handle each kind of work. Empty provider on basic chat /
          PR review falls back to default or investigation routing.
        </Typography.Paragraph>

        <Row gutter={[16, 12]} style={{ marginBottom: 20 }}>
          <Col xs={24} md={6}>
            <label className="alfred-field-label">Agentic skill routing</label>
            <Typography.Text type="secondary" style={{ display: "block", fontSize: 12 }}>
              When keyword triggers miss, use the Skill matching model below to pick a skill from
              the catalog (thread context included).
            </Typography.Text>
          </Col>
          <Col xs={24} md={18}>
            <Switch
              checked={config.skills.agentic_routing ?? true}
              onChange={(checked) =>
                updateConfig({
                  skills: { ...config.skills, agentic_routing: checked },
                })
              }
            />
            <Typography.Text type="secondary" style={{ marginLeft: 12, fontSize: 13 }}>
              {config.skills.agentic_routing ?? true ? "Enabled" : "Disabled — keywords and heuristics only"}
            </Typography.Text>
          </Col>
        </Row>

        {ROUTE_KEYS.map((key) => {
          const route = normalizeRoute(config.ai.routing[key]);
          const providerName = route.provider || config.ai.default_provider;
          const providerCfg = config.ai.providers[providerName];
          const modelOptions = modelOptionsForProvider(
            providerName,
            providerCfg?.model,
            route.model,
          );

          return (
            <Row gutter={[16, 12]} key={key} style={{ marginBottom: 12 }}>
              <Col xs={24} md={6}>
                <label className="alfred-field-label">{ROUTE_LABELS[key]}</label>
                <Typography.Text type="secondary" style={{ display: "block", fontSize: 12 }}>
                  {ROUTE_DESCRIPTIONS[key]}
                </Typography.Text>
              </Col>
              <Col xs={24} md={9}>
                <label className="alfred-field-label">Provider</label>
                <Select
                  style={{ width: "100%" }}
                  value={route.provider || undefined}
                  placeholder={`Default (${PROVIDER_LABELS[config.ai.default_provider] || config.ai.default_provider})`}
                  allowClear={key === "basic_chat" || key === "pr_review"}
                  options={allOptions}
                  getPopupContainer={(n) => n.parentElement ?? document.body}
                  onChange={(v) => updateRoute(key, { provider: v ?? "" })}
                />
              </Col>
              <Col xs={24} md={9}>
                <label className="alfred-field-label">Model</label>
                <AutoComplete
                  style={{ width: "100%" }}
                  value={route.model}
                  placeholder={
                    providerCfg?.model ? `Default (${providerCfg.model})` : "Provider default"
                  }
                  options={modelOptions.filter((o) => o.value !== "")}
                  getPopupContainer={(n) => n.parentElement ?? document.body}
                  onChange={(v) => updateRoute(key, { model: v ?? "" })}
                  onSelect={(v) => updateRoute(key, { model: v ?? "" })}
                  allowClear
                />
              </Col>
            </Row>
          );
        })}
      </div>

      <ActiveSections>
        {ALL_PROVIDERS.filter((name) => sections.isVisible(name)).map((name) => {
          const provider = config.ai.providers[name];
          if (!provider) return null;
          const help = AI_PROVIDER_HELP[name];
          const needsKey = name !== "ollama";

          return (
            <AddableSection
              key={name}
              title={PROVIDER_LABELS[name] || name}
              info={renderHelpContent(help)}
              visible
              configured={needsKey ? !!configured?.ai_api_keys?.[name] : true}
              onAdd={() => sections.add(name)}
              onRemove={() => {
                sections.remove(name);
                updateConfig({
                  ai: {
                    ...config.ai,
                    providers: {
                      ...config.ai.providers,
                      [name]: { ...provider, enabled: false },
                    },
                  },
                });
              }}
            >
              <Row gutter={[16, 12]}>
                <Col xs={24} md={12}>
                  <label className="alfred-field-label">Default model</label>
                  <Input
                    value={provider.model}
                    onChange={(e) =>
                      updateConfig({
                        ai: {
                          ...config.ai,
                          providers: {
                            ...config.ai.providers,
                            [name]: { ...provider, model: e.target.value, enabled: true },
                          },
                        },
                      })
                    }
                  />
                </Col>
                {(name === "ollama" || name === "openai" || name === "kimi") && (
                  <Col xs={24} md={12}>
                    <label className="alfred-field-label">Base URL</label>
                    <Input
                      value={provider.base_url}
                      onChange={(e) =>
                        updateConfig({
                          ai: {
                            ...config.ai,
                            providers: {
                              ...config.ai.providers,
                              [name]: { ...provider, base_url: e.target.value, enabled: true },
                            },
                          },
                        })
                      }
                    />
                  </Col>
                )}
              </Row>
              <div className="alfred-provider-actions">
                <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                  {needsKey
                    ? configured?.ai_api_keys?.[name]
                      ? "API key configured in Secrets"
                      : "Add API key in Secrets tab"
                    : "No API key required"}
                </Typography.Text>
                <Button size="small" onClick={() => testProvider(name)}>
                  Test connection
                </Button>
              </div>
            </AddableSection>
          );
        })}
      </ActiveSections>

      <AddableSectionList label={configuredIds.length > 0 ? "Providers" : "Add provider"}>
        {ALL_PROVIDERS.filter((name) => !sections.isVisible(name)).map((name) => (
          <AddableSection
            key={name}
            title={PROVIDER_LABELS[name] || name}
            info={renderHelpContent(AI_PROVIDER_HELP[name])}
            visible={false}
            configured={name !== "ollama" ? !!configured?.ai_api_keys?.[name] : true}
            onAdd={() => {
              sections.add(name);
              const provider = config.ai.providers[name];
              if (provider) {
                updateConfig({
                  ai: {
                    ...config.ai,
                    providers: {
                      ...config.ai.providers,
                      [name]: { ...provider, enabled: true },
                    },
                  },
                });
              }
            }}
            onRemove={() => {}}
          />
        ))}
      </AddableSectionList>

      <Button type="primary" onClick={saveConfig} style={{ marginTop: 24 }}>
        Save changes
      </Button>
    </div>
  );
}
