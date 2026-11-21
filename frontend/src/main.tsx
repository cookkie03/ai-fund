import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./lib/variant";
import { App } from "./App";
import "./index.css";
import "./variants.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
