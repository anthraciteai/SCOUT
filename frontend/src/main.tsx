import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { SelectionProvider } from "./selection";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <SelectionProvider>
        <App />
      </SelectionProvider>
    </BrowserRouter>
  </React.StrictMode>
);
