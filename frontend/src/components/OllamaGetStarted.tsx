import {
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DesktopOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RightOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import { Alert, Button, Collapse, Flex, Space, Spin, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, type OllamaStatus } from "../api/client";
import { showToast } from "../utils/toast";

type StepState = "pending" | "active" | "done";

function apiErrorMessage(err: unknown, fallback: string): string {
  const text = err instanceof Error ? err.message : fallback;
  if (text === "Not Found" || text.includes("404")) {
    return "Alfred API is out of date — restart the backend: ./scripts/dev.sh";
  }
  return text;
}

function stepState(done: boolean, prevDone: boolean): StepState {
  if (done) return "done";
  if (prevDone) return "active";
  return "pending";
}

function StepRow({
  label,
  state,
  detail,
}: {
  label: string;
  state: StepState;
  detail?: string;
}) {
  const configured = state === "done";
  return (
    <Flex
      gap={12}
      align="center"
      className={configured ? "alfred-ollama-step alfred-ollama-step-done" : "alfred-ollama-step"}
    >
      {configured ? (
        <CheckCircleOutlined style={{ color: "var(--alfred-accent)", fontSize: 14 }} />
      ) : state === "active" ? (
        <RightOutlined style={{ color: "var(--alfred-accent)", fontSize: 12 }} />
      ) : (
        <span className="alfred-ollama-step-dot" />
      )}
      <div className="alfred-ollama-step-body">
        <Typography.Text strong={state !== "pending"} type={configured ? "secondary" : undefined}>
          {label}
        </Typography.Text>
        {!configured && detail ? (
          <Typography.Paragraph type="secondary" style={{ margin: "2px 0 0", fontSize: 13 }}>
            {detail}
          </Typography.Paragraph>
        ) : null}
      </div>
    </Flex>
  );
}

function collapseSummary(
  installed: boolean,
  running: boolean,
  modelReady: boolean,
): string {
  if (!installed) return "Not installed — expand to download and configure.";
  if (!running) return "Installed — start the server to use local models.";
  if (!modelReady) return "Server running — pull a model to finish setup.";
  return "Ready for local inference.";
}

export function OllamaGetStarted({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setStatus(await api.ollamaStatus());
    } catch (err) {
      showToast("error", apiErrorMessage(err, "Could not load Ollama status"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const runAction = async (key: string, fn: () => Promise<{ ok: boolean; message?: string }>) => {
    setBusy(key);
    try {
      const result = await fn();
      if (result.ok) {
        showToast("success", result.message || "Done");
      } else {
        showToast("error", result.message || "Action failed");
      }
      await refresh();
    } catch (err) {
      showToast("error", apiErrorMessage(err, "Request failed"));
    } finally {
      setBusy(null);
    }
  };

  const installed = status?.installed ?? false;
  const running = status?.running ?? false;
  const modelReady = status?.model_ready ?? false;
  const ready = installed && running && modelReady;

  useEffect(() => {
    if (ready) {
      setExpanded(false);
    }
  }, [ready]);

  if (loading && !status) {
    return (
      <Flex justify="center" style={{ padding: compact ? 16 : 32 }}>
        <Spin />
      </Flex>
    );
  }

  const summary = collapseSummary(installed, running, modelReady);

  return (
    <div className="alfred-panel alfred-ollama-collapse-wrap">
      <Collapse
        bordered={false}
        className="alfred-ollama-collapse"
        activeKey={expanded ? ["ollama"] : []}
        onChange={(keys) => {
          const next = Array.isArray(keys) ? keys : [keys];
          setExpanded(next.includes("ollama"));
        }}
        items={[
          {
            key: "ollama",
            label: (
              <Flex gap={10} align="center" wrap="wrap" className="alfred-ollama-collapse-label">
                <DesktopOutlined style={{ color: "var(--alfred-accent)", fontSize: 16 }} />
                <Typography.Text strong>Get started with Ollama</Typography.Text>
                <Tag color="green">Local only</Tag>
                {!ready && installed ? <Tag color="default">Installed</Tag> : null}
                {ready ? <Tag color="success">Ready</Tag> : null}
                <Typography.Text type="secondary" className="alfred-ollama-collapse-summary">
                  {summary}
                </Typography.Text>
              </Flex>
            ),
            extra: (
              <Button
                size="small"
                type="text"
                icon={<ReloadOutlined />}
                onClick={(e) => {
                  e.stopPropagation();
                  refresh();
                }}
                loading={loading}
              >
                Refresh
              </Button>
            ),
            children: (
              <>
                {!ready ? (
                  <>
                    <Typography.Paragraph
                      type="secondary"
                      style={{ margin: "0 0 16px", maxWidth: 640, fontSize: 14 }}
                    >
                      Ollama runs AI on your machine — no cloud API key, no data leaving your network.
                      Alfred talks to it at{" "}
                      <Typography.Text code>{status?.api_url || "http://127.0.0.1:11434"}</Typography.Text>.
                    </Typography.Paragraph>

                    {status?.message && !installed ? (
                      <Alert
                        type="warning"
                        message={status.message}
                        showIcon
                        style={{ marginBottom: 16 }}
                      />
                    ) : null}
                  </>
                ) : null}

                <Flex vertical gap={ready ? 8 : 14} style={{ marginBottom: ready ? 12 : 20 }}>
                  <StepRow
                    label="Install Ollama"
                    state={stepState(installed, true)}
                    detail={installed ? status?.cli_path || "Installed" : status?.install_hint}
                  />
                  <StepRow
                    label="Start local server"
                    state={stepState(running, installed)}
                    detail={running ? "Server reachable" : "Run ollama serve or open the Ollama app"}
                  />
                  <StepRow
                    label={`Pull model (${status?.recommended_model || "llama3"})`}
                    state={stepState(modelReady, running)}
                    detail={
                      modelReady
                        ? "Model ready for Alfred"
                        : "First pull may take a few minutes depending on your connection"
                    }
                  />
                </Flex>

                {!ready ? (
                  <Space wrap>
                  <Button
                    type="primary"
                    icon={<RocketOutlined />}
                    loading={busy === "setup"}
                    disabled={!!busy || ready}
                    onClick={() => runAction("setup", () => api.ollamaSetup())}
                  >
                    {ready ? "Ready" : "Get started"}
                  </Button>
                  {!installed && (
                    <Button
                      icon={<CloudDownloadOutlined />}
                      loading={busy === "install"}
                      disabled={!!busy}
                      onClick={() => runAction("install", () => api.ollamaInstall())}
                    >
                      Install Ollama
                    </Button>
                  )}
                  {installed && !running && (
                    <Button
                      icon={<PlayCircleOutlined />}
                      loading={busy === "start"}
                      disabled={!!busy}
                      onClick={() => runAction("start", () => api.ollamaStart())}
                    >
                      Start server
                    </Button>
                  )}
                  {installed && running && !modelReady && (
                    <Button
                      icon={<CloudDownloadOutlined />}
                      loading={busy === "pull"}
                      disabled={!!busy}
                      onClick={() => runAction("pull", () => api.ollamaPull())}
                    >
                      Pull model
                    </Button>
                  )}
                  </Space>
                ) : (
                  <Typography.Text type="secondary">All setup steps complete.</Typography.Text>
                )}
              </>
            ),
          },
        ]}
      />
    </div>
  );
}
