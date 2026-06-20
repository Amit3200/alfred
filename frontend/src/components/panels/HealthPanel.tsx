import { Button, Flex, Typography } from "antd";
import { useApp } from "../../context/AppContext";
import { HealthChecksTable } from "../HealthChecksTable";

export function HealthPanel() {
  const { checks, runChecks } = useApp();

  return (
    <div className="alfred-settings-page">
      <Typography.Title level={3} className="alfred-page-title">
        Health
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        Verify connectivity to Slack, Git, AWS, and your configured AI provider.
      </Typography.Paragraph>

      <div className="alfred-panel">
        <Flex vertical gap={16}>
          <div>
            <Button type="primary" onClick={runChecks}>
              Run all checks
            </Button>
          </div>

          {!checks ? (
            <Typography.Text type="secondary">No checks run yet.</Typography.Text>
          ) : (
            <HealthChecksTable checks={checks} />
          )}
        </Flex>
      </div>
    </div>
  );
}
