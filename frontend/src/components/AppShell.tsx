import { Layout, Spin } from "antd";
import { AppSidebar } from "./AppSidebar";
import { ChatPage } from "./ChatPage";
import { HomePage } from "./HomePage";
import { LoginPage } from "./LoginPage";
import { AISettingsPanel } from "./panels/AISettingsPanel";
import { HealthPanel } from "./panels/HealthPanel";
import { IntegrationsPanel } from "./panels/IntegrationsPanel";
import { RepoMirrorsPanel } from "./panels/RepoMirrorsPanel";
import { PlaybooksPanel } from "./panels/PlaybooksPanel";
import { SecretsPanel } from "./panels/SecretsPanel";
import { UsagePanel } from "./panels/UsagePanel";
import { useApp } from "../context/AppContext";

const { Content } = Layout;
const SIDER_WIDTH = 248;

function SettingsContent() {
  const { settingsPage } = useApp();
  switch (settingsPage) {
    case "ai":
      return <AISettingsPanel />;
    case "secrets":
      return <SecretsPanel />;
    case "integrations":
      return <IntegrationsPanel />;
    case "repos":
      return <RepoMirrorsPanel />;
    case "playbooks":
      return <PlaybooksPanel />;
    case "health":
      return <HealthPanel />;
    case "usage":
      return <UsagePanel />;
    default:
      return <AISettingsPanel />;
  }
}

export function AppShell() {
  const { view, isAuthenticated, loading } = useApp();

  if (loading && !isAuthenticated) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", backgroundColor: "var(--alfred-bg)" }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <Layout hasSider className="alfred-shell">
      <AppSidebar width={SIDER_WIDTH} />
      <Layout className="alfred-main" style={{ marginLeft: SIDER_WIDTH }}>
        <Content className="alfred-main-inner">
          {view === "home" ? <HomePage /> : view === "chat" ? <ChatPage /> : <SettingsContent />}
        </Content>
      </Layout>
    </Layout>
  );
}
