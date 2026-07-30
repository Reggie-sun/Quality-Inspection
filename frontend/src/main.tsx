import { createRoot } from "react-dom/client";

import { QualityInspectionApp } from "./app/QualityInspectionApp";
import { clearCurrentProjectId } from "./app/localContext";
import { touchLocalDrawing } from "./app/localDrawingRegistry";
import { ProjectWorkbenchApp } from "./components/workbench/ProjectWorkbenchApp";
import "./styles/app.css";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("Missing #root element");
}

const parameters = new URLSearchParams(window.location.search);
const projectId = parameters.get("project_id")?.trim();
const operatorId = parameters.get("operator_id")?.trim();
const compatibilityLink = projectId !== undefined && projectId !== ""
  && operatorId !== undefined && operatorId !== "";

if (!compatibilityLink && (window.location.pathname !== "/" || window.location.search !== "")) {
  window.history.replaceState({}, "", "/");
}

createRoot(root).render(
  compatibilityLink
    ? (
      <ProjectWorkbenchApp
        projectId={projectId}
        operatorId={operatorId}
        onReset={() => {
          touchLocalDrawing(projectId, "未命名图纸.pdf");
          clearCurrentProjectId();
          window.location.assign("/");
        }}
      />
    )
    : <QualityInspectionApp />,
);
