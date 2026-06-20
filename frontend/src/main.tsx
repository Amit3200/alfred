import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AlfredToasts } from "./components/AlfredToasts";
import { ThemeProvider } from "./theme/ThemeProvider";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <AlfredToasts>
        <App />
      </AlfredToasts>
    </ThemeProvider>
  </StrictMode>,
);
