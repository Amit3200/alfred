import {
  ApiOutlined,
  BarChartOutlined,
  CommentOutlined,
  DatabaseOutlined,
  HeartOutlined,
  HomeOutlined,
  KeyOutlined,
  RobotOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { Logo } from "./Logo";
import { ThemeToggle } from "../theme/ThemeToggle";
import { useApp } from "../context/AppContext";
import type { SettingsPage } from "../types";

const { Sider } = Layout;

const SETTINGS_KEYS = new Set(["ai", "secrets", "integrations", "repos", "health", "usage"]);

type AppSidebarProps = {
  width: number;
};

export function AppSidebar({ width }: AppSidebarProps) {
  const { view, settingsPage, navigate, version } = useApp();

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

  return (
    <Sider
      width={width}
      className="alfred-shell-sider"
      theme="light"
      collapsedWidth={0}
      trigger={null}
    >
      <div className="alfred-sider-header">
        <Logo />
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
                { key: "ai", icon: <RobotOutlined />, label: "AI providers" },
                { key: "secrets", icon: <KeyOutlined />, label: "Secrets" },
                { key: "integrations", icon: <ApiOutlined />, label: "Integrations" },
                { key: "repos", icon: <DatabaseOutlined />, label: "Repo mirrors" },
                { key: "usage", icon: <BarChartOutlined />, label: "Usage" },
                { key: "health", icon: <HeartOutlined />, label: "Health" },
              ],
            },
          ]}
        />
      </div>

      <div className="alfred-sider-footer">
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          v{version || "0.1.0"}
        </Typography.Text>
        <ThemeToggle />
      </div>
    </Sider>
  );
}
