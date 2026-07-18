import {
  ApiOutlined,
  BankOutlined,
  BarChartOutlined,
  CodeOutlined,
  CommentOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HeartOutlined,
  HomeOutlined,
  KeyOutlined,
  LogoutOutlined,
  RobotOutlined,
  SettingOutlined,
  CalendarOutlined,
  FileSearchOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Typography, Select, Button } from "antd";
import { useEffect, useMemo, useState } from "react";
import { Logo } from "./Logo";
import { ALFRED_CREDIT } from "../branding";
import { ThemeToggle } from "../theme/ThemeToggle";
import { useTheme } from "../theme/ThemeProvider";
import { useApp } from "../context/AppContext";
import type { SettingsPage } from "../types";

const { Sider } = Layout;

const SETTINGS_KEYS = new Set(["branding", "ai", "secrets", "integrations", "repos", "playbooks", "scripts", "health", "usage", "schedules", "logs"]);

type AppSidebarProps = {
  width: number;
};

export function AppSidebar({ width }: AppSidebarProps) {
  const { view, settingsPage, navigate, version, logout, branding } = useApp();

  const selectedKeys = useMemo(
    () => (view === "home" ? ["home"] : view === "chat" ? ["chat"] : [settingsPage]),
    [view, settingsPage],
  );

  const [openKeys, setOpenKeys] = useState<string[]>(["settings"]);

  // Keep Configure expanded when viewing a settings page.
  useEffect(() => {
    if (view === "settings") {
      setOpenKeys((keys) => (keys.includes("settings") ? keys : [...keys, "settings"]));
    }
  }, [view]);

  const onOpenChange = (keys: string[]) => {
    setOpenKeys(keys);
  };

  const onSelect = ({ key }: { key: string }) => {
    if (key === "home") {
      navigate("home");
      return;
    }
    if (key === "chat") {
      navigate("chat");
      return;
    }
    if (SETTINGS_KEYS.has(key)) {
      navigate("settings", key as SettingsPage);
    }
  };

  const { themeVersion, setThemeVersion } = useTheme();

  return (
    <Sider
      width={width}
      className="alfred-shell-sider"
      theme="light"
      collapsedWidth={0}
      trigger={null}
    >
      <div className="alfred-sider-header">
        <Logo branding={branding} />
      </div>

      <div className="alfred-sider-nav">
        <Menu
          mode="inline"
          theme="light"
          selectedKeys={selectedKeys}
          openKeys={openKeys}
          onOpenChange={onOpenChange}
          onClick={onSelect}
          items={[
            { key: "home", icon: <HomeOutlined />, label: "Home" },
            { key: "chat", icon: <CommentOutlined />, label: "Chat" },
            {
              key: "settings",
              icon: <SettingOutlined />,
              label: "Configure",
              children: [
                { key: "branding", icon: <BankOutlined />, label: "Company profile" },
                { key: "ai", icon: <RobotOutlined />, label: "AI providers" },
                { key: "secrets", icon: <KeyOutlined />, label: "Secrets" },
                { key: "integrations", icon: <ApiOutlined />, label: "Integrations" },
                { key: "repos", icon: <DatabaseOutlined />, label: "Repo mirrors" },
                { key: "playbooks", icon: <FileTextOutlined />, label: "Playbooks" },
                { key: "scripts", icon: <CodeOutlined />, label: "Scripts" },
                { key: "schedules", icon: <CalendarOutlined />, label: "Schedules" },
                { key: "usage", icon: <BarChartOutlined />, label: "Usage" },
                { key: "logs", icon: <FileSearchOutlined />, label: "Logs" },
                { key: "health", icon: <HeartOutlined />, label: "Health" },
              ],
            },
          ]}
        />
      </div>

      <div className="alfred-sider-footer" style={{ flexDirection: "column", gap: 10, alignItems: "stretch" }}>
        <div>
          <Select
            size="small"
            value={themeVersion}
            onChange={(v) => setThemeVersion(v as "1.0" | "2.0")}
            options={[
              { label: "Theme 1.0 (Classic)", value: "1.0" },
              { label: "Theme 2.0 (Modern)", value: "2.0" }
            ]}
            style={{ width: "100%" }}
            getPopupContainer={(triggerNode) => triggerNode.parentNode}
          />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--alfred-border-subtle)", paddingTop: 8 }}>
          <div className="alfred-sider-footer-meta">
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              v{version || "0.1.0"}
            </Typography.Text>
            <a
              className="alfred-sider-credit"
              href={ALFRED_CREDIT.href}
              target="_blank"
              rel="noopener noreferrer"
            >
              {ALFRED_CREDIT.label}
            </a>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Button
              type="text"
              size="small"
              icon={<LogoutOutlined />}
              onClick={logout}
              title="Log out"
              style={{ color: "var(--alfred-text-muted)", padding: "0 4px", display: "flex", alignItems: "center", justifyContent: "center" }}
            />
            <ThemeToggle />
          </div>
        </div>
      </div>
    </Sider>
  );
}
