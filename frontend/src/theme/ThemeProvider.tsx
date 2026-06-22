import { App, ConfigProvider } from "antd";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  buildAntTheme,
  loadThemeMode,
  saveThemeMode,
  loadThemeVersion,
  saveThemeVersion,
  type ThemeMode,
  type ThemeVersion,
} from "./tokens";

type ThemeContextValue = {
  mode: ThemeMode;
  isDark: boolean;
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
  themeVersion: ThemeVersion;
  setThemeVersion: (version: ThemeVersion) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(() => loadThemeMode());
  const [themeVersion, setThemeVersion] = useState<ThemeVersion>(() => loadThemeVersion());

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", mode);
    saveThemeMode(mode);
  }, [mode]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme-version", themeVersion);
    saveThemeVersion(themeVersion);
  }, [themeVersion]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      isDark: mode === "dark",
      setMode,
      toggle: () => setMode((m) => (m === "dark" ? "light" : "dark")),
      themeVersion,
      setThemeVersion,
    }),
    [mode, themeVersion],
  );

  const antTheme = useMemo(() => buildAntTheme(mode, themeVersion), [mode, themeVersion]);

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
