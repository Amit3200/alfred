import { UploadOutlined } from "@ant-design/icons";
import { Button, Input, Modal, Typography, Upload } from "antd";
import type { UploadProps } from "antd";
import { useState } from "react";
import { api } from "../api/client";
import { Logo } from "./Logo";
import { useApp } from "../context/AppContext";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function BrandingSetupModal({ open, onClose }: Props) {
  const { config, updateConfig, refreshBranding, notify } = useApp();
  const [companyName, setCompanyName] = useState("");
  const [tagline, setTagline] = useState("Agent console");
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);

  const uploadProps: UploadProps = {
    accept: "image/png,image/jpeg,image/webp,image/svg+xml",
    showUploadList: false,
    beforeUpload: async (file) => {
      setUploading(true);
      try {
        await api.uploadBrandingLogo(file);
        await refreshBranding();
        notify("success", "Logo uploaded.");
      } catch (err) {
        notify("error", err instanceof Error ? err.message : "Logo upload failed");
      } finally {
        setUploading(false);
      }
      return false;
    },
  };

  const finish = async (skip: boolean) => {
    if (!config) return;
    setSaving(true);
    try {
      await api.updateBrandingProfile({
        company_name: skip ? "" : companyName.trim(),
        tagline: skip ? "Agent console" : tagline.trim() || "Agent console",
        setup_completed: true,
      });
      await refreshBranding();
      const cfg = await api.getConfig();
      updateConfig(cfg);
      onClose();
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Setup failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title="Set up your company profile"
      footer={null}
      onCancel={() => finish(true)}
      width={520}
    >
      <Typography.Paragraph type="secondary">
        Optional — personalize Alfred for your team. You can change this anytime under Configure →
        Company profile.
      </Typography.Paragraph>

      <div style={{ marginBottom: 16 }}>
        <Logo
          branding={{
            company_name: companyName,
            tagline,
            display_title: companyName.trim() ? `Alfred × ${companyName.trim()}` : "Alfred",
            setup_completed: false,
            has_logo: false,
            logo_url: "",
          }}
          size="md"
        />
      </div>

      <label className="alfred-field-label">Company name</label>
      <Input
        value={companyName}
        placeholder="Acme Corp"
        onChange={(e) => setCompanyName(e.target.value)}
        style={{ marginBottom: 12 }}
      />

      <label className="alfred-field-label">Tagline</label>
      <Input
        value={tagline}
        placeholder="Agent console"
        onChange={(e) => setTagline(e.target.value)}
        style={{ marginBottom: 16 }}
      />

      <Upload {...uploadProps}>
        <Button icon={<UploadOutlined />} loading={uploading} style={{ marginBottom: 16 }}>
          Upload company logo (optional)
        </Button>
      </Upload>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <Button onClick={() => finish(true)} disabled={saving}>
          Skip for now
        </Button>
        <Button type="primary" onClick={() => finish(false)} loading={saving}>
          Save and continue
        </Button>
      </div>
    </Modal>
  );
}
