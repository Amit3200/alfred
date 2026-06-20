import { MoonOutlined, SunOutlined } from "@ant-design/icons";
import { Segmented } from "antd";
import { useTheme } from "./ThemeProvider";

export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  return (
    <Segmented
      size="small"
      value={mode}
      onChange={(v) => setMode(v as "light" | "dark")}
      options={[
        { value: "light", icon: <SunOutlined /> },
        { value: "dark", icon: <MoonOutlined /> },
      ]}
    />
  );
}
