import { createRoot } from "react-dom/client";

import { ProjectWorkbenchApp } from "./components/workbench/ProjectWorkbenchApp";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("Missing #root element");
}

const style = document.createElement("style");
style.textContent = `
  :root {
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #172033;
    background: #f6f7fb;
    font-synthesis: none;
  }
  * { box-sizing: border-box; }
  body { margin: 0; min-width: 1024px; background: #f6f7fb; }
  button, input, select { font: inherit; }
  button {
    min-height: 36px;
    padding: 7px 12px;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    background: #ffffff;
    color: #1e293b;
    cursor: pointer;
  }
  button:hover:not(:disabled) { border-color: #7c3aed; color: #6d28d9; }
  button:focus-visible, input:focus-visible, select:focus-visible {
    outline: 3px solid #c4b5fd;
    outline-offset: 2px;
  }
  button:disabled { cursor: not-allowed; color: #94a3b8; background: #f1f5f9; }
  input, select {
    min-height: 34px;
    min-width: 0;
    padding: 6px 8px;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    background: #ffffff;
    color: #172033;
  }
  fieldset { border: 1px solid #dbe2ea; border-radius: 8px; margin: 10px 0; padding: 10px; }
  legend { color: #475569; font-weight: 650; padding: 0 5px; }
  [role="row"] > label {
    display: grid !important;
    grid-template-columns: minmax(145px, 0.9fr) minmax(0, 1.1fr);
    align-items: center;
    gap: 8px;
    margin-bottom: 7px;
    font-size: 13px;
  }
  [role="row"] > label:first-child {
    grid-template-columns: 20px minmax(0, 1fr);
    color: #475569;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  [role="row"] input:not([type="checkbox"]), [role="row"] select { width: 100%; }
`;
document.head.append(style);

const parameters = new URLSearchParams(window.location.search);
const projectId = parameters.get("project_id")?.trim();
const operatorId = parameters.get("operator_id")?.trim();

createRoot(root).render(
  projectId === undefined || projectId === "" || operatorId === undefined || operatorId === ""
    ? (
      <main role="alert">
        A real project_id and operator_id are required to open the review workbench.
      </main>
    )
    : <ProjectWorkbenchApp projectId={projectId} operatorId={operatorId} />,
);
