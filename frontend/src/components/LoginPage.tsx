import { useState } from "react";
import { Form, Input, Button, Typography } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { useApp } from "../context/AppContext";
import { Logo } from "./Logo";

export function LoginPage() {
  const { login } = useApp();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: any) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
    } catch (err) {
      // Errors are already handled and toasted by the login method in context
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="alfred-login-container">
      <div className="alfred-login-glow-1" />
      <div className="alfred-login-glow-2" />
      <div className="alfred-login-card">
        <div className="alfred-login-header">
          <div className="alfred-login-logo">
            <Logo compact size="lg" />
          </div>
          <Typography.Title level={3} className="alfred-login-title" style={{ margin: 0 }}>
            Welcome back
          </Typography.Title>
          <Typography.Text className="alfred-login-desc">
            Sign in to manage your Alfred console
          </Typography.Text>
        </div>
        <Form
          name="login"
          onFinish={onFinish}
          layout="vertical"
          requiredMark={false}
          className="alfred-login-form"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: "Please input your username!" }]}
          >
            <Input
              prefix={<UserOutlined style={{ color: "var(--alfred-text-faint)" }} />}
              placeholder="Username"
              size="large"
            />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: "Please input your password or token!" }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: "var(--alfred-text-faint)" }} />}
              placeholder="Password or Token"
              size="large"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              className="alfred-login-button"
              size="large"
            >
              Sign In
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  );
}
