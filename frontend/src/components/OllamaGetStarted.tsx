import {
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DesktopOutlined,
  LoadingOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import { Alert, Button, Flex, Space, Spin, Tag, Typography } from "antd";
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
  return (
    <Flex gap={12} align="flex-start">
      {state === "done" ? (
        <CheckCircleOutlined style={{ color: "var(--alfred-accent)", marginTop: 2 }} />
      ) : state === "active" ? (
        <LoadingOutlined style={{ color: "var(--alfred-accent)", marginTop: 2 }} />
      ) : (
        <span className="alfred-ollama-step-dot" />
      )}
      <div>
        <Typography.Text strong={state !== "pending"}>{label}</Typography.Text>
        {detail && (
          <Typography.Paragraph type="secondary" style={{ margin: "2px 0 0", fontSize: 13 }}>
            {detail}
          </Typography.Paragraph>
        )}
      </div>
    </Flex>
  );
}

export function OllamaGetStarted({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

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

  if (loading && !status) {
    return (
      <Flex justify="center" style={{ padding: compact ? 16 : 32 }}>
        <Spin />
      </Flex>
    );
  }

  const installed = status?.installed ?? false;
  const running = status?.running ?? false;
  const modelReady = status?.model_ready ?? false;
  const ready = installed && running && modelReady;

  return (
    <div className={compact ? undefined : "alfred-panel"}>
      <Flex justify="space-between" align="flex-start" wrap="wrap" gap={12} style={{ marginBottom: 16 }}>
        <div>
          <Flex gap={10} align="center" style={{ marginBottom: 6 }}>
            <DesktopOutlined style={{ color: "var(--alfred-accent)", fontSize: 18 }} />
            <Typography.Title level={compact ? 5 : 4} style={{ margin: 0 }}>
              Get started with Ollama
            </Typography.Title>
            <Tag color="green">Local only</Tag>
          </Flex>
          <Typography.Paragraph type="secondary" style={{ margin: 0, maxWidth: 640, fontSize: 14 }}>
            Ollama runs AI on your machine — no cloud API key, no data leaving your network. Alfred
            talks to it at <Typography.Text code>{status?.api_url || "http://127.0.0.1:11434"}</Typography.Text>.
          </Typography.Paragraph>
        </div>
        <Button size="small" icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
          Refresh
        </Button>
      </Flex>

      {status?.message && (
        <Alert
          type={ready ? "success" : installed ? "info" : "warning"}
          message={status.message}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Flex vertical gap={14} style={{ marginBottom: 20 }}>
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
    </div>
  );
}
