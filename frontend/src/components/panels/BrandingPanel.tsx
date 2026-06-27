import { PictureOutlined, UploadOutlined } from "@ant-design/icons";
import { Button, Col, Input, Row, Typography, Upload } from "antd";
import type { UploadProps } from "antd";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Logo } from "../Logo";
import { useApp } from "../../context/AppContext";

export function BrandingPanel() {
  const { config, updateConfig, branding, refreshBranding, notify } = useApp();
  const [uploading, setUploading] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [tagline, setTagline] = useState("Agent console");

  useEffect(() => {
    if (!config) return;
    setCompanyName(config.branding?.company_name || "");
    setTagline(config.branding?.tagline || "Agent console");
  }, [config]);

  if (!config) {
    return <Typography.Text type="secondary">Loading configuration…</Typography.Text>;
  }

  const uploadProps: UploadProps = {
    accept: "image/png,image/jpeg,image/webp,image/svg+xml",
    showUploadList: false,
    beforeUpload: async (file) => {
      setUploading(true);
      try {
        const snapshot = await api.uploadBrandingLogo(file);
        await refreshBranding();
        const cfg = await api.getConfig();
        updateConfig(cfg);
        notify("success", "Logo uploaded.");
      } catch (err) {
        notify("error", err instanceof Error ? err.message : "Logo upload failed");
      } finally {
        setUploading(false);
      }
      return false;
    },
  };

  const saveProfile = async () => {
    try {
      await api.updateBrandingProfile({
        company_name: companyName.trim(),
        tagline: tagline.trim() || "Agent console",
        setup_completed: true,
      });
      await refreshBranding();
      const cfg = await api.getConfig();
      updateConfig(cfg);
      notify("success", "Branding saved.");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Save failed");
    }
  };

  const removeLogo = async () => {
    try {
      await api.deleteBrandingLogo();
      await refreshBranding();
      notify("success", "Logo removed.");
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Remove failed");
    }
  };

  return (
    <div className="alfred-settings-page">
      <Typography.Title level={3} className="alfred-page-title">
        Company profile
      </Typography.Title>
      <Typography.Paragraph className="alfred-page-desc">
        White-label Alfred for your team — shown in the admin console as{" "}
        <Typography.Text code>Alfred × Your company</Typography.Text>.
      </Typography.Paragraph>

      <div className="alfred-panel" style={{ marginBottom: 20 }}>
        <Typography.Title level={5} style={{ marginTop: 0 }}>
          Preview
        </Typography.Title>
        <Logo branding={branding} size="lg" />
      </div>

      <div className="alfred-panel" style={{ marginBottom: 20 }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <label className="alfred-field-label">Company name</label>
            <Input
              value={companyName}
              placeholder="Acme Corp"
              onChange={(e) => setCompanyName(e.target.value)}
            />
          </Col>
          <Col xs={24} md={12}>
            <label className="alfred-field-label">Tagline</label>
            <Input
              value={tagline}
              placeholder="Agent console"
              onChange={(e) => setTagline(e.target.value)}
            />
          </Col>
        </Row>
        <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Button type="primary" onClick={saveProfile}>
            Save profile
          </Button>
        </div>
      </div>

      <div className="alfred-panel">
        <Typography.Title level={5} style={{ marginTop: 0 }}>
          Company logo
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
          PNG, JPG, WebP, or SVG — max 2 MB. Shown beside the Alfred mark in the sidebar and login
          screen.
        </Typography.Paragraph>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <Upload {...uploadProps}>
            <Button icon={<UploadOutlined />} loading={uploading}>
              Upload logo
            </Button>
          </Upload>
          {branding?.has_logo && (
            <Button icon={<PictureOutlined />} onClick={removeLogo}>
              Remove logo
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
