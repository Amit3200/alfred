import type { ThemeConfig } from "antd";
import { theme } from "antd";

export type ThemeMode = "light" | "dark";

export const THEME_STORAGE_KEY = "alfred-theme";

const FONT =
  'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

export function loadThemeMode(): ThemeMode {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function saveThemeMode(mode: ThemeMode) {
  localStorage.setItem(THEME_STORAGE_KEY, mode);
}

export function buildAntTheme(mode: ThemeMode): ThemeConfig {
  const isDark = mode === "dark";

  return {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: isDark ? "#d4a853" : "#9a6b2f",
      colorPrimaryHover: isDark ? "#e8c876" : "#7d5624",
      colorPrimaryActive: isDark ? "#c9a04a" : "#6b481f",
      borderRadius: 8,
      borderRadiusSM: 6,
      borderRadiusLG: 12,
      fontSize: 14,
      fontSizeSM: 12,
      controlHeight: 36,
      controlHeightSM: 30,
      lineWidthFocus: 1,
      colorBorder: isDark ? "#2e2a26" : "#ddd5c8",
      colorBorderSecondary: isDark ? "#252220" : "#ebe4d9",
      colorBgLayout: isDark ? "#121110" : "#f0ebe3",
      colorBgContainer: isDark ? "#1a1816" : "#fffcf7",
      colorBgElevated: isDark ? "#201e1b" : "#ffffff",
      colorText: isDark ? "#e7e2db" : "#1c1917",
      colorTextSecondary: isDark ? "#a39e96" : "#6b6560",
      colorFillSecondary: isDark ? "#252220" : "#f5f0e8",
      fontFamily: FONT,
    },
    components: {
      Button: {
        primaryShadow: "none",
        defaultShadow: "none",
        fontWeight: 500,
        primaryColor: isDark ? "#121110" : "#fffcf7",
        defaultBg: isDark ? "#201e1b" : "#fffcf7",
        defaultBorderColor: isDark ? "#2e2a26" : "#ddd5c8",
        defaultColor: isDark ? "#d6d0c7" : "#44403c",
        defaultHoverBg: isDark ? "#2a2724" : "#f5f0e8",
      },
      Input: {
        activeShadow: isDark
          ? "0 0 0 2px rgba(212, 168, 83, 0.2)"
          : "0 0 0 2px rgba(154, 107, 47, 0.15)",
      },
      Select: {
        optionSelectedBg: isDark ? "#2a2724" : "#f5f0e8",
      },
      Menu: {
        itemBg: "transparent",
        subMenuItemBg: "transparent",
        itemSelectedBg: isDark ? "rgba(212, 168, 83, 0.12)" : "rgba(154, 107, 47, 0.1)",
        itemSelectedColor: isDark ? "#e8c876" : "#9a6b2f",
        itemHoverBg: isDark ? "#252220" : "#f5f0e8",
      },
      Layout: {
        siderBg: isDark ? "#161412" : "#f5f0e8",
        bodyBg: isDark ? "#121110" : "#f0ebe3",
      },
      Notification: {
        colorBgElevated: isDark ? "#1a1816" : "#fffcf7",
        colorText: isDark ? "#e7e2db" : "#1c1917",
        colorTextHeading: isDark ? "#faf8f5" : "#0c0a09",
        colorIcon: isDark ? "#d4a853" : "#9a6b2f",
        colorIconHover: isDark ? "#e8c876" : "#7d5624",
        colorError: isDark ? "#f08080" : "#c45c5c",
        colorSuccess: isDark ? "#6ecf96" : "#3d7a54",
        colorWarning: isDark ? "#e8c876" : "#9a6b2f",
        colorInfo: isDark ? "#a39e96" : "#6b6560",
        paddingContentVerticalLG: 14,
        paddingContentHorizontalLG: 16,
        borderRadiusLG: 14,
      },
      Typography: {
        fontFamilyCode: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      },
    },
  };
}

export { FONT };
