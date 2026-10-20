import "@fontsource-variable/instrument-sans/wdth.css";
import "@fontsource/ibm-plex-mono/400.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";

import { App } from "./App";
import { routes } from "./routes";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html has no #root element to render into");
}

// Vite's base, without the trailing slash the router doesn't expect.
const router = createBrowserRouter(routes, {
  basename: import.meta.env.BASE_URL.replace(/\/$/, ""),
});

createRoot(root).render(
  <StrictMode>
    <App router={router} />
  </StrictMode>,
);
