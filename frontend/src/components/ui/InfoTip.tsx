import { InfoCircleOutlined } from "@ant-design/icons";
import { Popover } from "antd";
import type { ReactNode } from "react";

type InfoTipProps = {
  content: ReactNode;
  title?: string;
};

export function InfoTip({ content, title }: InfoTipProps) {
  return (
    <Popover
      title={title}
      content={content}
      trigger="click"
      placement="rightTop"
      overlayClassName="alfred-help-popover-overlay"
      getPopupContainer={() => document.getElementById("alfred-root") ?? document.body}
    >
      <button type="button" className="alfred-info-btn" aria-label="More information">
        <InfoCircleOutlined />
      </button>
    </Popover>
  );
}
