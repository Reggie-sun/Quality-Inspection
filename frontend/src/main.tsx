import { createRoot } from "react-dom/client";

import { QualityInspectionApp } from "./app/QualityInspectionApp";
import { clearCurrentProjectId, isUuid } from "./app/localContext";
import { ProjectWorkbenchApp } from "./components/workbench/ProjectWorkbenchApp";
import "./styles/app.css";


export function returnFromCompatibilityLink(
  _projectId: string,
  navigate: (path: string) => void = (path) => window.location.assign(path),
): void {
  clearCurrentProjectId();
  navigate("/");
}


const root = document.getElementById("root");

if (root === null) {
  throw new Error("Missing #root element");
}

const parameters = new URLSearchParams(window.location.search);
const projectId = parameters.get("project_id")?.trim();
const operatorId = parameters.get("operator_id")?.trim();
const compatibilityLink = isUuid(projectId)
  && operatorId !== undefined
  && operatorId !== "";

if (!compatibilityLink && (window.location.pathname !== "/" || window.location.search !== "")) {
  window.history.replaceState({}, "", "/");
}

createRoot(root).render(
  compatibilityLink
    ? (
      <ProjectWorkbenchApp
        projectId={projectId}
        operatorId={operatorId}
        onReset={() => returnFromCompatibilityLink(projectId)}
      />
    )
    : <QualityInspectionApp />,
);
