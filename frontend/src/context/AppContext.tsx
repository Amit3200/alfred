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
  PublicBranding,
  SecretsPayload,
  api,
  getAdminToken,
  setAdminToken,
  ApiError,
} from "../api/client";
import { defaultPublicBranding } from "../branding";
import type { HealthCheck } from "../health";
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
  branding: PublicBranding;
  checks: Record<string, HealthCheck> | null;
  view: AppView;
  settingsPage: SettingsPage;
  navigate: (view: AppView, settingsPage?: SettingsPage) => void;
  isAuthenticated: boolean;
  login: (username: string, password_or_token: string) => Promise<void>;
  logout: () => void;
  load: () => Promise<void>;
  saveToken: () => void;
  updateConfig: (patch: Partial<AlfredConfig>) => void;
  saveConfig: () => Promise<void>;
  saveSecrets: () => Promise<void>;
  runChecks: () => Promise<void>;
  testProvider: (name: string) => Promise<void>;
  testIntegration: (name: string) => Promise<void>;
  refreshBranding: () => Promise<void>;
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
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(!!getAdminToken());
  const [loading, setLoading] = useState(true);
  const [checks, setChecks] = useState<AppContextValue["checks"]>(null);
  const [version, setVersion] = useState("");
  const [dataDir, setDataDir] = useState("");
  const [initialized, setInitialized] = useState(false);
  const [branding, setBranding] = useState<PublicBranding>(defaultPublicBranding());
  const parsePath = useCallback((): { view: AppView; settingsPage: SettingsPage } => {
    const path = window.location.pathname;
    if (path.startsWith("/chat")) {
      return { view: "chat", settingsPage: "ai" };
    }
    if (path.startsWith("/settings/")) {
      const page = path.substring("/settings/".length) as SettingsPage;
      return { view: "settings", settingsPage: page };
    }
    return { view: "home", settingsPage: "ai" };
  }, []);

  const [view, setView] = useState<AppView>(() => parsePath().view);
  const [settingsPage, setSettingsPage] = useState<SettingsPage>(() => parsePath().settingsPage);

  const notify = useCallback((type: "error" | "success", text: string) => {
    showToast(type, text);
  }, []);

  const refreshBranding = useCallback(async () => {
    try {
      setBranding(await api.getPublicBranding());
    } catch {
      setBranding(defaultPublicBranding());
    }
  }, []);

  const refreshChecks = useCallback(async () => {
    try {
      setChecks(await api.checks());
    } catch {
      setChecks(null);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const health = await api.health();
      setVersion(health.version);
      setDataDir(health.data_dir || "");
      setInitialized(health.initialized);
      await refreshBranding();
      setIsAuthenticated(true);
      if (health.initialized) {
        const cfg = await api.getConfig();
        setConfig(cfg);
        await refreshChecks();
      } else {
        setConfig(null);
        setChecks(null);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setIsAuthenticated(false);
        setAdminToken("");
        setTokenInput("");
        try {
          setBranding(await api.getPublicBranding());
        } catch {
          setBranding(defaultPublicBranding());
        }
      } else {
        notify("error", err instanceof Error ? err.message : "Failed to load");
      }
      setConfig(null);
    } finally {
      setLoading(false);
    }
  }, [notify, refreshBranding, refreshChecks]);

  const login = async (username: string, password_or_token: string) => {
    setLoading(true);
    try {
      let token = "";
      if (username.trim() && password_or_token.trim()) {
        const res = await api.login(username, password_or_token);
        token = res.token;
      } else {
        token = (password_or_token || username).trim();
      }
      if (!token) {
        throw new Error("Username and password or token is required");
      }
      setAdminToken(token);
      setTokenInput(token);
      setIsAuthenticated(true);
      await load();
      notify("success", "Logged in successfully");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Login failed");
      setIsAuthenticated(false);
      setAdminToken("");
      setTokenInput("");
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    setAdminToken("");
    setTokenInput("");
    setIsAuthenticated(false);
    setConfig(null);
    setChecks(null);
    notify("success", "Logged out successfully");
  };

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handlePopState = () => {
      const current = parsePath();
      setView(current.view);
      setSettingsPage(current.settingsPage);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [parsePath]);

  const navigate = (nextView: AppView, page?: SettingsPage) => {
    setView(nextView);
    if (page) setSettingsPage(page);
    
    // Sync browser URL history
    let path = "/";
    if (nextView === "chat") {
      path = "/chat";
    } else if (nextView === "settings") {
      path = `/settings/${page || settingsPage}`;
    }
    
    if (window.location.pathname !== path) {
      window.history.pushState(null, "", path);
    }
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
      await refreshChecks();
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
      await refreshChecks();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Save failed");
    }
  };

  const runChecks = async () => {
    try {
      setChecks(await api.checks());
    } catch (err) {
      setChecks(null);
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
      try {
        await refreshChecks();
      } catch {
        setChecks((prev) => ({ ...(prev ?? {}), [name]: result }));
      }
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
        isAuthenticated,
        login,
        logout,
        loading,
        version,
        dataDir,
        initialized,
        branding,
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
        refreshBranding,
        notify,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
