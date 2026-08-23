import { Button, Input, Typography } from "antd";
import {
  AI_KEY_HELP,
  SECRETS_HELP,
  renderHelpContent,
} from "../../content/helpText";
import { useApp } from "../../context/AppContext";
import { useSectionVisibility } from "../../hooks/useSectionVisibility";
import {
  ActiveSections,
  AddableSection,
  AddableSectionList,
} from "../ui/AddableSection";
import { JsonCredentialField } from "../ui/JsonCredentialField";


const AI_KEY_IDS = ["openai", "anthropic", "gemini", "kimi"] as const;

export function SecretsPanel() {
  const { config, secrets, setSecrets, saveSecrets, tokenInput, setTokenInput, saveToken, dataDir } =
    useApp();

  const integrations = useSectionVisibility("secrets-integrations");
  const aiKeys = useSectionVisibility("secrets-ai-keys");

  if (!config) {
    return <Typography.Text type="secondary">Loading configuration…</Typography.Text>;
  }

  const configured = config._secrets_configured;

  const slackConfigured = !!(
    configured?.slack_bot_token ||
    configured?.slack_signing_secret ||
    configured?.slack_app_token
  );
  const gitConfigured = !!configured?.git_token;
  const githubConfigured = !!(
    configured?.github_webhook_secret || configured?.github_client_secret
  );
  const awsConfigured = !!(
    configured?.aws_access_key_id || configured?.aws_secret_access_key
  );
  const jiraConfigured = !!configured?.jira_api_token;
  const periskopeConfigured = !!(
    configured?.connectors?.periskope?.api_token ||
    configured?.connectors?.periskope?.webhook_secret
  );
  const googleConfigured = !!configured?.google_credentials_json;
  const webSearchConfigured = !!configured?.web_search_api_key;

  return (
    <div>
      <Typography.Title level={3} className="alfred-page-title">
        Secrets
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Add only the integrations you need. Values are encrypted at rest — leave fields blank to
        keep existing secrets.
      </Typography.Paragraph>

      <div className="alfred-panel" style={{ marginBottom: 20 }}>
        <div className="alfred-section-title">Admin token</div>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 14 }}>
          Required for Chat and saving secrets. From the project directory run:{" "}
          <Typography.Text code>alfred token</Typography.Text>
          {dataDir && (
            <>
              <br />
              Server data dir: <Typography.Text code>{dataDir}</Typography.Text>
            </>
          )}
        </Typography.Paragraph>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Input.Password
            placeholder="Admin token from alfred init"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            style={{ flex: 1, minWidth: 220 }}
          />
          <Button type="primary" onClick={saveToken}>
            Save token
          </Button>
        </div>
      </div>

      <ActiveSections>
        {integrations.isVisible("slack") && (
          <AddableSection
            title="Slack"
            info={renderHelpContent(SECRETS_HELP.slack)}
            visible
            configured={slackConfigured}
            onAdd={() => integrations.add("slack")}
            onRemove={() => integrations.remove("slack")}
          >
            <SecretField
              label="Bot token (xoxb-)"
              configured={configured?.slack_bot_token}
              storedHint={configured?.slack_bot_token_hint}
              invalid={!!configured?.slack_bot_token && configured?.slack_bot_token_valid === false}
              value={secrets.slack_bot_token ?? ""}
              placeholder="xoxb-..."
              onChange={(v) => setSecrets((s) => ({ ...s, slack_bot_token: v }))}
            />
            <SecretField
              label="Signing secret"
              configured={configured?.slack_signing_secret}
              value={secrets.slack_signing_secret ?? ""}
              onChange={(v) => setSecrets((s) => ({ ...s, slack_signing_secret: v }))}
            />
            <SecretField
              label="App token — Socket Mode (xapp-)"
              configured={configured?.slack_app_token}
              value={secrets.slack_app_token ?? ""}
              hint="Optional. Use when not exposing a public webhook."
              onChange={(v) => setSecrets((s) => ({ ...s, slack_app_token: v }))}
            />
          </AddableSection>
        )}

        {integrations.isVisible("git") && (
          <AddableSection
            title="Git"
            info={renderHelpContent(SECRETS_HELP.git)}
            visible
            configured={gitConfigured}
            onAdd={() => integrations.add("git")}
            onRemove={() => integrations.remove("git")}
          >
            <SecretField
              label="Personal access token"
              configured={configured?.git_token}
              hint="Also used to post PR review replies on GitHub."
              onChange={(v) => setSecrets((s) => ({ ...s, git_token: v }))}
            />
          </AddableSection>
        )}

        {integrations.isVisible("github") && (
          <AddableSection
            title="GitHub App"
            info={renderHelpContent(SECRETS_HELP.github)}
            visible
            configured={githubConfigured}
            onAdd={() => integrations.add("github")}
            onRemove={() => integrations.remove("github")}
          >
            <SecretField
              label="Webhook secret"
              configured={configured?.github_webhook_secret}
              hint="Same value as GitHub App → Webhook → Secret."
              onChange={(v) => setSecrets((s) => ({ ...s, github_webhook_secret: v }))}
            />
            <SecretField
              label="Client secret (optional)"
              configured={configured?.github_client_secret}
              hint="From GitHub App settings — only needed for OAuth callback."
              onChange={(v) => setSecrets((s) => ({ ...s, github_client_secret: v }))}
            />
          </AddableSection>
        )}

        {integrations.isVisible("aws") && (
          <AddableSection
            title="AWS"
            info={renderHelpContent(SECRETS_HELP.aws)}
            visible
            configured={awsConfigured}
            onAdd={() => integrations.add("aws")}
            onRemove={() => integrations.remove("aws")}
          >
            <SecretField
              label="Access key ID"
              configured={configured?.aws_access_key_id}
              onChange={(v) => setSecrets((s) => ({ ...s, aws_access_key_id: v }))}
            />
            <SecretField
              label="Secret access key"
              configured={configured?.aws_secret_access_key}
              onChange={(v) => setSecrets((s) => ({ ...s, aws_secret_access_key: v }))}
            />
          </AddableSection>
        )}

        {integrations.isVisible("jira") && (
          <AddableSection
            title="JIRA"
            info={renderHelpContent(SECRETS_HELP.jira)}
            visible
            configured={jiraConfigured}
            onAdd={() => integrations.add("jira")}
            onRemove={() => integrations.remove("jira")}
          >
            <SecretField
              label="API token"
              configured={configured?.jira_api_token}
              onChange={(v) => setSecrets((s) => ({ ...s, jira_api_token: v }))}
            />
          </AddableSection>
        )}

        {integrations.isVisible("periskope") && (
          <AddableSection
            title="Periskope"
            info={renderHelpContent(SECRETS_HELP.periskope)}
            visible
            configured={periskopeConfigured}
            onAdd={() => integrations.add("periskope")}
            onRemove={() => integrations.remove("periskope")}
          >
            <SecretField
              label="API token"
              configured={configured?.connectors?.periskope?.api_token}
              onChange={(v) =>
                setSecrets((s) => ({
                  ...s,
                  connectors: {
                    ...(s.connectors || {}),
                    periskope: { ...(s.connectors?.periskope || {}), api_token: v },
                  },
                }))
              }
            />
            <SecretField
              label="Webhook signing key"
              configured={configured?.connectors?.periskope?.webhook_secret}
              onChange={(v) =>
                setSecrets((s) => ({
                  ...s,
                  connectors: {
                    ...(s.connectors || {}),
                    periskope: { ...(s.connectors?.periskope || {}), webhook_secret: v },
                  },
                }))
              }
            />
          </AddableSection>
        )}

        {integrations.isVisible("google") && (
          <AddableSection
            title="Google Workspace"
            info={renderHelpContent(SECRETS_HELP.google)}
            visible
            configured={googleConfigured}
            onAdd={() => integrations.add("google")}
            onRemove={() => integrations.remove("google")}
          >
            <JsonCredentialField
              label="OAuth client or service account JSON"
              configured={configured?.google_credentials_json}
              credentialType={configured?.google_credentials_type}
              oauthConnected={configured?.google_oauth_connected}
              value={secrets.google_credentials_json ?? ""}
              onChange={(v) => setSecrets((s) => ({ ...s, google_credentials_json: v }))}
            />
          </AddableSection>
        )}

        {integrations.isVisible("web_search") && (
          <AddableSection
            title="Web search (Tavily)"
            info={renderHelpContent(SECRETS_HELP.web_search)}
            visible
            configured={webSearchConfigured}
            onAdd={() => integrations.add("web_search")}
            onRemove={() => integrations.remove("web_search")}
          >
            <SecretField
              label="Tavily API key"
              configured={configured?.web_search_api_key}
              value={secrets.web_search_api_key ?? ""}
              placeholder="tvly-..."
              hint="Only required when Integrations → Web search uses the Tavily provider."
              onChange={(v) => setSecrets((s) => ({ ...s, web_search_api_key: v }))}
            />
          </AddableSection>
        )}
      </ActiveSections>

      <AddableSectionList
        label={
          slackConfigured || gitConfigured || githubConfigured || awsConfigured || jiraConfigured || periskopeConfigured || googleConfigured || webSearchConfigured
            ? "Integrations"
            : "Add integration"
        }
      >
        {!integrations.isVisible("slack") && (
          <AddableSection
            title="Slack"
            info={renderHelpContent(SECRETS_HELP.slack)}
            visible={false}
            configured={slackConfigured}
            onAdd={() => integrations.add("slack")}
            onRemove={() => {}}
          />
        )}
        {!integrations.isVisible("git") && (
          <AddableSection
            title="Git"
            info={renderHelpContent(SECRETS_HELP.git)}
            visible={false}
            configured={gitConfigured}
            onAdd={() => integrations.add("git")}
            onRemove={() => {}}
          />
        )}
        {!integrations.isVisible("github") && (
          <AddableSection
            title="GitHub App"
            info={renderHelpContent(SECRETS_HELP.github)}
            visible={false}
            configured={githubConfigured}
            onAdd={() => integrations.add("github")}
            onRemove={() => {}}
          />
        )}
        {!integrations.isVisible("aws") && (
          <AddableSection
            title="AWS"
            info={renderHelpContent(SECRETS_HELP.aws)}
            visible={false}
            configured={awsConfigured}
            onAdd={() => integrations.add("aws")}
            onRemove={() => {}}
          />
        )}
        {!integrations.isVisible("jira") && (
          <AddableSection
            title="JIRA"
            info={renderHelpContent(SECRETS_HELP.jira)}
            visible={false}
            configured={jiraConfigured}
            onAdd={() => integrations.add("jira")}
            onRemove={() => {}}
          />
        )}
        {!integrations.isVisible("periskope") && (
          <AddableSection
            title="Periskope"
            info={renderHelpContent(SECRETS_HELP.periskope)}
            visible={false}
            configured={periskopeConfigured}
            onAdd={() => integrations.add("periskope")}
            onRemove={() => {}}
          />
        )}
        {!integrations.isVisible("google") && (
          <AddableSection
            title="Google Workspace"
            info={renderHelpContent(SECRETS_HELP.google)}
            visible={false}
            configured={googleConfigured}
            onAdd={() => integrations.add("google")}
            onRemove={() => {}}
          />
        )}
        {!integrations.isVisible("web_search") && (
          <AddableSection
            title="Web search (Tavily)"
            info={renderHelpContent(SECRETS_HELP.web_search)}
            visible={false}
            configured={webSearchConfigured}
            onAdd={() => integrations.add("web_search")}
            onRemove={() => {}}
          />
        )}
      </AddableSectionList>

      <Typography.Title level={5} style={{ marginTop: 32, marginBottom: 8, fontWeight: 600 }}>
        AI API keys
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16, fontSize: 14 }}>
        Cloud providers need keys here. Ollama runs locally — configure it on the AI providers page.
      </Typography.Paragraph>

      <ActiveSections>
        {AI_KEY_IDS.filter((id) => aiKeys.isVisible(`ai-${id}`)).map((id) => {
          const help = AI_KEY_HELP[id];
          const label = id === "anthropic" ? "Claude" : id.charAt(0).toUpperCase() + id.slice(1);
          const sectionId = `ai-${id}`;
          return (
            <AddableSection
              key={id}
              title={label}
              info={renderHelpContent(help)}
              visible
              configured={!!configured?.ai_api_keys?.[id]}
              onAdd={() => aiKeys.add(sectionId)}
              onRemove={() => aiKeys.remove(sectionId)}
            >
              <SecretField
                label="API key"
                configured={configured?.ai_api_keys?.[id]}
                placeholder="sk-..."
                onChange={(v) =>
                  setSecrets((s) => ({
                    ...s,
                    ai_api_keys: { ...s.ai_api_keys, [id]: v },
                  }))
                }
              />
            </AddableSection>
          );
        })}
      </ActiveSections>

      <AddableSectionList
        label={
          AI_KEY_IDS.some((id) => configured?.ai_api_keys?.[id]) ? "AI keys" : "Add AI key"
        }
      >
        {AI_KEY_IDS.filter((id) => !aiKeys.isVisible(`ai-${id}`)).map((id) => {
          const label = id === "anthropic" ? "Claude" : id.charAt(0).toUpperCase() + id.slice(1);
          return (
            <AddableSection
              key={id}
              title={label}
              info={renderHelpContent(AI_KEY_HELP[id])}
              visible={false}
              configured={!!configured?.ai_api_keys?.[id]}
              onAdd={() => aiKeys.add(`ai-${id}`)}
              onRemove={() => {}}
            />
          );
        })}
      </AddableSectionList>

      <Button type="primary" onClick={saveSecrets} style={{ marginTop: 24 }}>
        Save secrets
      </Button>
    </div>
  );
}

function SecretField({
  label,
  configured,
  storedHint,
  invalid,
  placeholder,
  hint,
  value,
  onChange,
}: {
  label: string;
  configured?: boolean;
  storedHint?: string | null;
  invalid?: boolean;
  placeholder?: string;
  hint?: string;
  value?: string;
  onChange: (value: string) => void;
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label className="alfred-field-label">
        {label}
        {configured ? (
          <span
            className={`alfred-status-chip alfred-status-chip-sm${invalid ? " alfred-status-chip-warn" : ""}`}
          >
            {invalid ? "Re-save" : "Saved"}
          </span>
        ) : null}
      </label>
      <Input.Password
        value={value}
        placeholder={
          configured ? "Paste new value to replace what is stored" : placeholder
        }
        onChange={(e) => onChange(e.target.value)}
      />
      {configured && storedHint && (
        <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: "block" }}>
          Stored: <Typography.Text code>{storedHint}</Typography.Text>
        </Typography.Text>
      )}
      {invalid && (
        <Typography.Text type="danger" style={{ fontSize: 12, marginTop: 4, display: "block" }}>
          Stored token is not a valid xoxb- bot token. Paste your full token above and click Save
          secrets.
        </Typography.Text>
      )}
      {configured && !invalid && (
        <Typography.Text type="success" style={{ fontSize: 12, marginTop: 4, display: "block" }}>
          Encrypted on disk. Values are never shown again after save.
        </Typography.Text>
      )}
      {hint && (
        <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: "block" }}>
          {hint}
        </Typography.Text>
      )}
    </div>
  );
}
