import { MinusOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Flex, Typography } from "antd";
import type { ReactNode } from "react";
import { InfoTip } from "./InfoTip";

function StatusChip({ label }: { label: string }) {
  return <span className="alfred-status-chip">{label}</span>;
}

type AddableSectionProps = {
  title: string;
  info: ReactNode;
  infoTitle?: string;
  visible: boolean;
  configured?: boolean;
  onAdd: () => void;
  onRemove: () => void;
  children: ReactNode;
};

export function AddableSection({
  title,
  info,
  infoTitle,
  visible,
  configured,
  onAdd,
  onRemove,
  children,
}: AddableSectionProps) {
  if (!visible) {
    return (
      <div className="alfred-add-chip">
        <button type="button" className="alfred-add-chip-main" onClick={onAdd}>
          <PlusOutlined />
          <span>{title}</span>
          {configured && <StatusChip label="Configured" />}
        </button>
        <InfoTip content={info} title={infoTitle || title} />
      </div>
    );
  }

  return (
    <div className="alfred-integration-block">
      <Flex justify="space-between" align="center" className="alfred-integration-block-header">
        <Flex align="center" gap={8}>
          <Typography.Text strong>{title}</Typography.Text>
          {configured && <StatusChip label="Configured" />}
          <InfoTip content={info} title={infoTitle || title} />
        </Flex>
        <Button
          type="text"
          size="small"
          icon={<MinusOutlined />}
          onClick={onRemove}
          aria-label={`Remove ${title}`}
          className="alfred-remove-btn"
        />
      </Flex>
      <div className="alfred-integration-block-body">{children}</div>
    </div>
  );
}

export function AddableSectionList({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div className="alfred-integration-list">
      {label && <div className="alfred-section-title">{label}</div>}
      <div className="alfred-add-chip-row">{children}</div>
    </div>
  );
}

export function ActiveSections({ children }: { children: ReactNode }) {
  return <div className="alfred-active-sections">{children}</div>;
}
