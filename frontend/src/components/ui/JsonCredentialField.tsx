import { UploadOutlined } from "@ant-design/icons";
import { Button, Input, Typography, Upload } from "antd";
import type { UploadProps } from "antd";
import { useState } from "react";

type JsonCredentialFieldProps = {
  label: string;
  configured?: boolean;
  credentialType?: string | null;
  oauthConnected?: boolean;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
};

export function JsonCredentialField({
  label,
  configured,
  credentialType,
  oauthConnected,
  value,
  onChange,
  hint,
}: JsonCredentialFieldProps) {
  const [uploadName, setUploadName] = useState<string | null>(null);

  const readFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      onChange(String(reader.result ?? ""));
      setUploadName(file.name);
    };
    reader.readAsText(file);
  };

  const uploadProps: UploadProps = {
    accept: "application/json,.json",
    showUploadList: false,
    multiple: false,
    beforeUpload: (file) => {
      readFile(file);
      return false;
    },
  };

  let statusHint = hint ?? "";
  if (!statusHint && configured && credentialType === "service_account") {
    statusHint = "Service account JSON saved — share Sheets/Docs with the service account email.";
  } else if (!statusHint && configured && credentialType === "oauth_client") {
    statusHint = oauthConnected
      ? "OAuth client saved and connected."
      : "OAuth client saved — click Connect Google below.";
  } else if (!statusHint && configured && credentialType === "invalid") {
    statusHint = "Saved JSON could not be parsed — upload a valid OAuth client or service account file.";
  }

  return (
    <div style={{ marginBottom: 14 }}>
      <label className="alfred-field-label">
        {label}
        {configured ? (
          <span className="alfred-status-chip alfred-status-chip-sm">Saved</span>
        ) : null}
      </label>

      <Upload.Dragger {...uploadProps} style={{ marginBottom: 10 }}>
        <p className="ant-upload-drag-icon">
          <UploadOutlined />
        </p>
        <p className="ant-upload-text">Drop credentials.json here, or click to browse</p>
        <p className="ant-upload-hint" style={{ fontSize: 12 }}>
          OAuth client JSON (web/installed) or Google service account key
        </p>
      </Upload.Dragger>

      {uploadName && (
        <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
          Loaded file: <Typography.Text code>{uploadName}</Typography.Text>
        </Typography.Text>
      )}

      <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
        Or paste JSON below
      </Typography.Text>
      <Input.TextArea
        value={value}
        rows={5}
        placeholder={
          configured
            ? "Paste new JSON to replace what is stored"
            : '{"web":{"client_id":"...","client_secret":"..."}}'
        }
        onChange={(e) => {
          onChange(e.target.value);
          if (e.target.value.trim()) setUploadName(null);
        }}
        style={{ fontFamily: "monospace", fontSize: 12 }}
      />

      <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
        <Upload {...uploadProps}>
          <Button size="small" icon={<UploadOutlined />}>
            Choose file
          </Button>
        </Upload>
        {configured && (
          <Typography.Text type="success" style={{ fontSize: 12, alignSelf: "center" }}>
            Encrypted on disk — JSON is not shown again after save.
          </Typography.Text>
        )}
      </div>

      {statusHint && (
        <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 6, display: "block" }}>
          {statusHint}
        </Typography.Text>
      )}
    </div>
  );
}
