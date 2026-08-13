import { Layout, Spin } from "antd";
import { useState } from "react";
import { BrandingSetupModal } from "./BrandingSetupModal";
import { AppSidebar } from "./AppSidebar";
import { ChatPage } from "./ChatPage";
import { HomePage } from "./HomePage";
import { LoginPage } from "./LoginPage";
import { KnowledgePanel } from "./panels/KnowledgePanel";
import { BrandingPanel } from "./panels/BrandingPanel";
import { AISettingsPanel } from "./panels/AISettingsPanel";
import { HealthPanel } from "./panels/HealthPanel";
import { IntegrationsPanel } from "./panels/IntegrationsPanel";
import { RepoMirrorsPanel } from "./panels/RepoMirrorsPanel";
import { PlaybooksPanel } from "./panels/PlaybooksPanel";
import { ScriptsPanel } from "./panels/ScriptsPanel";
import { ArtifactsPanel } from "./panels/ArtifactsPanel";
import { SecretsPanel } from "./panels/SecretsPanel";
import { UsagePanel } from "./panels/UsagePanel";
import { SchedulesPanel } from "./panels/SchedulesPanel";
import { SlackBoardsPanel } from "./panels/SlackBoardsPanel";
import { LogsPanel } from "./panels/LogsPanel";
import { ToolsPanel } from "./panels/ToolsPanel";
import { RoutingPanel } from "./panels/RoutingPanel";
import { useApp } from "../context/AppContext";

const { Content } = Layout;
const SIDER_WIDTH = 248;

function SettingsContent() {
  const { settingsPage } = useApp();
  switch (settingsPage) {
    case "branding":
      return <BrandingPanel />;
    case "ai":
      return <AISettingsPanel />;
    case "secrets":
      return <SecretsPanel />;
    case "integrations":
      return <IntegrationsPanel />;
    case "knowledge":
      return <KnowledgePanel />;
    case "repos":
      return <RepoMirrorsPanel />;
    case "playbooks":
      return <PlaybooksPanel />;
    case "scripts":
      return <ScriptsPanel />;
    case "artifacts":
      return <ArtifactsPanel />;
    case "tools":
      return <ToolsPanel />;
    case "routing":
      return <RoutingPanel />;
    case "health":
      return <HealthPanel />;
    case "usage":
      return <UsagePanel />;
    case "schedules":
      return <SchedulesPanel />;
    case "slack-boards":
      return <SlackBoardsPanel />;
    case "logs":
      return <LogsPanel />;
    default:
      return <AISettingsPanel />;
  }
}

export function AppShell() {
  const { view, isAuthenticated, loading, config } = useApp();
  const [setupDismissed, setSetupDismissed] = useState(false);
  const showBrandingSetup =
    isAuthenticated &&
    config &&
    !config.branding?.setup_completed &&
    !setupDismissed;

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
    <>
      <BrandingSetupModal open={showBrandingSetup} onClose={() => setSetupDismissed(true)} />
      <Layout hasSider className="alfred-shell">
        <AppSidebar width={SIDER_WIDTH} />
        <Layout className="alfred-main" style={{ marginLeft: SIDER_WIDTH }}>
          <Content className="alfred-main-inner">
            {view === "home" ? <HomePage /> : view === "chat" ? <ChatPage /> : <SettingsContent />}
          </Content>
        </Layout>
      </Layout>
    </>
  );
}
