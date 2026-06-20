import { App, ConfigProvider } from "antd";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { buildAntTheme, loadThemeMode, saveThemeMode, type ThemeMode } from "./tokens";

type ThemeContextValue = {
  mode: ThemeMode;
  isDark: boolean;
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(() => loadThemeMode());

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", mode);
    saveThemeMode(mode);
  }, [mode]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      isDark: mode === "dark",
      setMode,
      toggle: () => setMode((m) => (m === "dark" ? "light" : "dark")),
    }),
    [mode],
  );

  const antTheme = useMemo(() => buildAntTheme(mode), [mode]);

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider theme={antTheme} getPopupContainer={() => document.getElementById("alfred-root") ?? document.body}>
        <App className="alfred-app">
          <div id="alfred-root">{children}</div>
        </App>
      </ConfigProvider>
    </ThemeContext.Provider>
  );
}
