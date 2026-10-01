import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import App from "./App.jsx";


const savedTheme =
  localStorage.getItem(
    "devpilot_theme"
  ) === "dark"
    ? "dark"
    : "light";


document.documentElement.setAttribute(
  "data-theme",
  savedTheme
);


createRoot(
  document.getElementById("root")
).render(
  <StrictMode>
    <App />
  </StrictMode>
);