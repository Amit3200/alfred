import type { ThemeConfig } from "antd";
import { theme } from "antd";

export type ThemeMode = "light" | "dark";
export type ThemeVersion = "1.0" | "2.0";

export const THEME_STORAGE_KEY = "alfred-theme";
export const THEME_VERSION_STORAGE_KEY = "alfred-theme-version";

const FONT = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
const FONT_V2 = '"Plus Jakarta Sans", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

export function loadThemeMode(): ThemeMode {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function saveThemeMode(mode: ThemeMode) {
  localStorage.setItem(THEME_STORAGE_KEY, mode);
}

export function loadThemeVersion(): ThemeVersion {
  const stored = localStorage.getItem(THEME_VERSION_STORAGE_KEY);
  if (stored === "1.0" || stored === "2.0") return stored;
  return "1.0";
}

export function saveThemeVersion(version: ThemeVersion) {
  localStorage.setItem(THEME_VERSION_STORAGE_KEY, version);
}

export function buildAntTheme(mode: ThemeMode, version: ThemeVersion = "1.0"): ThemeConfig {
  const isDark = mode === "dark";
  const isV2 = version === "2.0";

  const primaryColor = isV2 
    ? (isDark ? "#818cf8" : "#4f46e5") 
    : (isDark ? "#d4a853" : "#9a6b2f");
  const primaryHoverColor = isV2 
    ? (isDark ? "#a5b4fc" : "#4338ca") 
    : (isDark ? "#e8c876" : "#7d5624");
  const primaryActiveColor = isV2 
    ? (isDark ? "#6366f1" : "#3730a3") 
    : (isDark ? "#c9a04a" : "#6b481f");

  const borderRadius = isV2 ? 4 : 8;
  const borderRadiusSM = isV2 ? 2 : 6;
  const borderRadiusLG = isV2 ? 6 : 12;

  const font = isV2 ? FONT_V2 : FONT;

  return {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: primaryColor,
      colorPrimaryHover: primaryHoverColor,
      colorPrimaryActive: primaryActiveColor,
      borderRadius,
      borderRadiusSM,
      borderRadiusLG,
      fontSize: isV2 ? 13 : 14,
      fontSizeSM: isV2 ? 11 : 12,
      controlHeight: 36,
      controlHeightSM: 30,
      lineWidthFocus: 1,
      colorBorder: isV2 
        ? (isDark ? "#1e293b" : "#e2e8f0")
        : (isDark ? "#2e2a26" : "#ddd5c8"),
      colorBorderSecondary: isV2
        ? (isDark ? "#0d1321" : "#f1f5f9")
        : (isDark ? "#252220" : "#ebe4d9"),
      colorBgLayout: isV2
        ? (isDark ? "#090d16" : "#f8fafc")
        : (isDark ? "#121110" : "#f0ebe3"),
      colorBgContainer: isV2
        ? (isDark ? "#131c2e" : "#ffffff")
        : (isDark ? "#1a1816" : "#fffcf7"),
      colorBgElevated: isV2
        ? (isDark ? "#1e293b" : "#ffffff")
        : (isDark ? "#201e1b" : "#ffffff"),
      colorText: isV2
        ? (isDark ? "#cbd5e1" : "#334155")
        : (isDark ? "#e7e2db" : "#1c1917"),
      colorTextSecondary: isV2
        ? (isDark ? "#94a3b8" : "#64748b")
        : (isDark ? "#a39e96" : "#6b6560"),
      colorFillSecondary: isV2
        ? (isDark ? "#0d1321" : "#f1f5f9")
        : (isDark ? "#252220" : "#f5f0e8"),
      fontFamily: font,
    },
    components: {
      Button: {
        primaryShadow: "none",
        defaultShadow: "none",
        fontWeight: 500,
        primaryColor: isDark 
          ? (isV2 ? "#090d16" : "#121110") 
          : (isV2 ? "#ffffff" : "#fffcf7"),
        defaultBg: isDark 
          ? (isV2 ? "#1e293b" : "#201e1b") 
          : (isV2 ? "#ffffff" : "#fffcf7"),
        defaultBorderColor: isV2
          ? (isDark ? "#1e293b" : "#e2e8f0")
          : (isDark ? "#2e2a26" : "#ddd5c8"),
        defaultColor: isV2
          ? (isDark ? "#cbd5e1" : "#334155")
          : (isDark ? "#d6d0c7" : "#44403c"),
        defaultHoverBg: isV2
          ? (isDark ? "#334155" : "#f8fafc")
          : (isDark ? "#2a2724" : "#f5f0e8"),
      },
      Input: {
        activeShadow: isV2
          ? (isDark ? "0 0 0 2px rgba(129, 140, 248, 0.2)" : "0 0 0 2px rgba(79, 70, 229, 0.15)")
          : (isDark ? "0 0 0 2px rgba(212, 168, 83, 0.2)" : "0 0 0 2px rgba(154, 107, 47, 0.15)"),
      },
      Select: {
        optionSelectedBg: isV2
          ? (isDark ? "#1e293b" : "#f1f5f9")
          : (isDark ? "#2a2724" : "#f5f0e8"),
      },
      Menu: {
        itemBg: "transparent",
        subMenuItemBg: "transparent",
        itemSelectedBg: isV2
          ? (isDark ? "rgba(129, 140, 248, 0.12)" : "rgba(79, 70, 229, 0.08)")
          : (isDark ? "rgba(212, 168, 83, 0.12)" : "rgba(154, 107, 47, 0.1)"),
        itemSelectedColor: isV2
          ? (isDark ? "#a5b4fc" : "#4f46e5")
          : (isDark ? "#e8c876" : "#9a6b2f"),
        itemHoverBg: isV2
          ? (isDark ? "#0d1321" : "#f1f5f9")
          : (isDark ? "#252220" : "#f5f0e8"),
      },
      Layout: {
        siderBg: isV2
          ? (isDark ? "#0d1321" : "#f1f5f9")
          : (isDark ? "#161412" : "#f5f0e8"),
        bodyBg: isV2
          ? (isDark ? "#090d16" : "#f8fafc")
          : (isDark ? "#121110" : "#f0ebe3"),
      },
      Notification: {
        colorBgElevated: isV2
          ? (isDark ? "#131c2e" : "#ffffff")
          : (isDark ? "#1a1816" : "#fffcf7"),
        colorText: isV2
          ? (isDark ? "#cbd5e1" : "#334155")
          : (isDark ? "#e7e2db" : "#1c1917"),
        colorTextHeading: isV2
          ? (isDark ? "#f8fafc" : "#0f172a")
          : (isDark ? "#faf8f5" : "#0c0a09"),
        colorIcon: isV2
          ? (isDark ? "#818cf8" : "#4f46e5")
          : (isDark ? "#d4a853" : "#9a6b2f"),
        colorIconHover: isV2
          ? (isDark ? "#a5b4fc" : "#4338ca")
          : (isDark ? "#e8c876" : "#7d5624"),
        colorError: isDark ? "#f08080" : "#c45c5c",
        colorSuccess: isDark ? "#6ecf96" : "#3d7a54",
        colorWarning: isV2
          ? (isDark ? "#818cf8" : "#4f46e5")
          : (isDark ? "#e8c876" : "#9a6b2f"),
        colorInfo: isV2
          ? (isDark ? "#94a3b8" : "#64748b")
          : (isDark ? "#a39e96" : "#6b6560"),
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
