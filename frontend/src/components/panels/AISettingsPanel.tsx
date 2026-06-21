import { Button, Col, Input, Row, Select, Typography } from "antd";
import { useMemo } from "react";
import { AI_PROVIDER_HELP, renderHelpContent } from "../../content/helpText";
import { useApp } from "../../context/AppContext";
import { useSectionVisibility } from "../../hooks/useSectionVisibility";
import { PROVIDER_LABELS } from "../../types";
import {
  ActiveSections,
  AddableSection,
  AddableSectionList,
} from "../ui/AddableSection";
import { OllamaGetStarted } from "../OllamaGetStarted";

const ALL_PROVIDERS = ["ollama", "openai", "anthropic", "gemini", "kimi"] as const;

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

  return (
    <div className="alfred-settings-page">
      <Typography.Title level={3} className="alfred-page-title">
        AI providers
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Add providers you want to use. Set routing defaults below — skill matching can use a cheap
        local model, investigation a capable cloud model.
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
          <Col xs={24} md={8}>
            <label className="alfred-field-label">Skill matching</label>
            <Select
              style={{ width: "100%" }}
              value={config.ai.routing.skill_matching}
              options={allOptions}
              getPopupContainer={(n) => n.parentElement ?? document.body}
              onChange={(v) =>
                updateConfig({
                  ai: { ...config.ai, routing: { ...config.ai.routing, skill_matching: v } },
                })
              }
            />
          </Col>
          <Col xs={24} md={8}>
            <label className="alfred-field-label">Investigation</label>
            <Select
              style={{ width: "100%" }}
              value={config.ai.routing.investigation}
              options={allOptions}
              getPopupContainer={(n) => n.parentElement ?? document.body}
              onChange={(v) =>
                updateConfig({
                  ai: { ...config.ai, routing: { ...config.ai.routing, investigation: v } },
                })
              }
            />
          </Col>
        </Row>
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
                  <label className="alfred-field-label">Model</label>
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
