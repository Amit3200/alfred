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


const AI_KEY_IDS = ["openai", "anthropic", "gemini"] as const;

export function SecretsPanel() {
  const { config, secrets, setSecrets, saveSecrets, tokenInput, setTokenInput, dataDir } =
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
  const awsConfigured = !!(
    configured?.aws_access_key_id || configured?.aws_secret_access_key
  );

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
          Required to save secrets. From the project directory run:{" "}
          <Typography.Text code>alfred token</Typography.Text>
          {dataDir && (
            <>
              <br />
              Server data dir: <Typography.Text code>{dataDir}</Typography.Text>
            </>
          )}
        </Typography.Paragraph>
        <Input.Password
          placeholder="Admin token from alfred init"
          value={tokenInput}
          onChange={(e) => setTokenInput(e.target.value)}
        />
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
              onChange={(v) => setSecrets((s) => ({ ...s, git_token: v }))}
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
      </ActiveSections>

      <AddableSectionList
        label={
          slackConfigured || gitConfigured || awsConfigured ? "Integrations" : "Add integration"
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
