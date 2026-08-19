// Copyright (c) Microsoft. All rights reserved.

import React from "react";
import ReactDOM from "react-dom/client";

import "@openuidev/react-ui/components.css";
import "@openuidev/react-ui/styles/index.css";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
