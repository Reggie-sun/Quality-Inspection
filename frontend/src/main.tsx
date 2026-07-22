import { createRoot } from "react-dom/client";

import { InspectionWorkbench } from "./components/workbench/InspectionWorkbench";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("Missing #root element");
}

createRoot(root).render(
  <InspectionWorkbench
    pdfDocument={null}
    pageCount={2}
    candidates={[
      { id: "candidate-1", pageIndex: 0, bbox: [90, 80, 240, 125] },
      { id: "candidate-2", pageIndex: 1, bbox: [180, 150, 310, 195] },
    ]}
    sources={[{ id: "source-1", pageIndex: 0, bbox: [70, 65, 260, 140] }]}
    balloons={[{ id: "balloon-1", pageIndex: 0, center: [280, 100], number: 1 }]}
    pageTransforms={[
      { pageIndex: 0, pdfToRenderMatrix: [0, 2, -2, 0, 1440, 0] },
      { pageIndex: 1, pdfToRenderMatrix: [2, 0, 0, 2, 0, 0] },
    ]}
    items={[
      {
        item_id: "candidate-1",
        item_type: "thread",
        raw_text: "M6 通",
        coordinates: [90, 80, 240, 125],
        scope: "local_feature",
        balloon_required: true,
        requires_confirmation: false,
        active: true,
      },
      {
        item_id: "candidate-2",
        item_type: "linear_dimension",
        raw_text: "10 ±0.02",
        coordinates: [180, 150, 310, 195],
        scope: "local_feature",
        balloon_required: true,
        requires_confirmation: false,
        active: true,
      },
    ]}
    onSave={async () => {
      throw new Error("No project is loaded in the local workbench preview");
    }}
  />,
);
