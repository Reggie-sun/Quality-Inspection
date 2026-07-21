import React from "react";
import { createRoot } from "react-dom/client";


const root = document.getElementById("root");

if (root === null) {
  throw new Error("Missing #root element");
}

createRoot(root).render(
  <main>
    <h1>Quality Inspection</h1>
  </main>,
);
