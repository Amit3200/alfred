import { Layout } from "antd";
import { AppSidebar } from "./AppSidebar";
import { HomePage } from "./HomePage";
import { AISettingsPanel } from "./panels/AISettingsPanel";
import { HealthPanel } from "./panels/HealthPanel";
import { IntegrationsPanel } from "./panels/IntegrationsPanel";
import { SecretsPanel } from "./panels/SecretsPanel";
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
    case "health":
      return <HealthPanel />;
    default:
      return <AISettingsPanel />;
  }
}

export function AppShell() {
  const { view } = useApp();

  return (
    <Layout hasSider className="alfred-shell">
      <AppSidebar width={SIDER_WIDTH} />
      <Layout className="alfred-main" style={{ marginLeft: SIDER_WIDTH }}>
        <Content className="alfred-main-inner">
          {view === "home" ? <HomePage /> : <SettingsContent />}
        </Content>
      </Layout>
    </Layout>
  );
}
