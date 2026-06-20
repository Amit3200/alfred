import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  AlfredConfig,
  SecretsPayload,
  api,
  getAdminToken,
  setAdminToken,
} from "../api/client";
import type { AppView, SettingsPage } from "../types";
import { showToast } from "../utils/toast";

type AppContextValue = {
  config: AlfredConfig | null;
  secrets: SecretsPayload;
  setSecrets: React.Dispatch<React.SetStateAction<SecretsPayload>>;
  tokenInput: string;
  setTokenInput: (v: string) => void;
  loading: boolean;
  version: string;
  initialized: boolean;
  dataDir: string;
  checks: Record<string, { ok: boolean; message?: string; skipped?: boolean }> | null;
  view: AppView;
  settingsPage: SettingsPage;
  navigate: (view: AppView, settingsPage?: SettingsPage) => void;
  load: () => Promise<void>;
  saveToken: () => void;
  updateConfig: (patch: Partial<AlfredConfig>) => void;
  saveConfig: () => Promise<void>;
  saveSecrets: () => Promise<void>;
  runChecks: () => Promise<void>;
  testProvider: (name: string) => Promise<void>;
  testIntegration: (name: string) => Promise<void>;
  notify: (type: "error" | "success", text: string) => void;
};

const AppContext = createContext<AppContextValue | null>(null);

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AlfredConfig | null>(null);
  const [secrets, setSecrets] = useState<SecretsPayload>({ ai_api_keys: {} });
  const [tokenInput, setTokenInput] = useState(getAdminToken());
  const [loading, setLoading] = useState(true);
  const [checks, setChecks] = useState<AppContextValue["checks"]>(null);
  const [version, setVersion] = useState("");
  const [dataDir, setDataDir] = useState("");
  const [initialized, setInitialized] = useState(false);
  const [view, setView] = useState<AppView>("home");
  const [settingsPage, setSettingsPage] = useState<SettingsPage>("ai");

  const notify = useCallback((type: "error" | "success", text: string) => {
    showToast(type, text);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const health = await api.health();
      setVersion(health.version);
      setDataDir(health.data_dir || "");
      setInitialized(health.initialized);
      if (health.initialized) {
        const cfg = await api.getConfig();
        setConfig(cfg);
      } else {
        setConfig(null);
      }
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Failed to load");
      setConfig(null);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  const navigate = (nextView: AppView, page?: SettingsPage) => {
    setView(nextView);
    if (page) setSettingsPage(page);
  };

  const saveToken = () => {
    setAdminToken(tokenInput.trim());
    notify("success", "Admin token saved.");
  };

  const updateConfig = (patch: Partial<AlfredConfig>) => {
    if (!config) return;
    setConfig({ ...config, ...patch });
  };

  const persistAdminToken = (): string | null => {
    const token = tokenInput.trim();
    if (!token) return null;
    setAdminToken(token);
    return token;
  };

  const saveConfig = async () => {
    if (!config) return;
    const token = persistAdminToken();
    if (!token) {
      notify("error", "Admin token required — paste the token from alfred init.");
      return;
    }
    try {
      setConfig(await api.saveConfig(config, token));
      notify("success", "Configuration saved.");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Save failed");
    }
  };

  const saveSecrets = async () => {
    const token = persistAdminToken();
    if (!token) {
      notify("error", "Admin token required — paste the token from alfred init.");
      return;
    }
    try {
      setConfig(await api.saveSecrets(secrets, token));
      setSecrets({ ai_api_keys: {} });
      notify("success", "Secrets saved (encrypted).");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Save failed");
    }
  };

  const runChecks = async () => {
    try {
      setChecks(await api.checks());
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Checks failed");
    }
  };

  const testProvider = async (name: string) => {
    try {
      const result = await api.testProvider(name);
      notify(
        result.ok ? "success" : "error",
        result.ok ? `${name}: ${result.reply || "OK"}` : `${name}: ${result.message || "Failed"}`,
      );
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Test failed");
    }
  };

  const testIntegration = async (name: string) => {
    try {
      const result = await api.testIntegration(name);
      notify(
        result.ok ? "success" : "error",
        `${name}: ${result.message || (result.ok ? "OK" : "Failed")}`,
      );
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Test failed");
    }
  };

  return (
    <AppContext.Provider
      value={{
        config,
        secrets,
        setSecrets,
        tokenInput,
        setTokenInput,
        loading,
        version,
        dataDir,
        initialized,
        checks,
        view,
        settingsPage,
        navigate,
        load,
        saveToken,
        updateConfig,
        saveConfig,
        saveSecrets,
        runChecks,
        testProvider,
        testIntegration,
        notify,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
