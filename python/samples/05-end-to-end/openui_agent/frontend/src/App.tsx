// Copyright (c) Microsoft. All rights reserved.

import { useMemo } from "react";
import { AgentInterface, createTheme, type ThemeProps } from "@openuidev/react-ui";

import { createAgentFrameworkLLM } from "./agent-framework";
import { library } from "./openui-library";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8894";

const microsoftTheme: ThemeProps = {
  mode: "light",
  lightTheme: createTheme({
    background: "#f5f9ff",
    interactiveAccentDefault: "#2563eb",
    chatUserResponseBg: "#dbeafe",
    chatUserResponseText: "#172554",
    radiusM: "12px",
    fontBody: '"Segoe UI", Inter, system-ui, sans-serif',
  }),
};

const starters = [
  {
    displayText: "View quarterly revenue",
    prompt: "Show me our quarterly revenue.",
  },
  {
    displayText: "Estimate a project",
    prompt: "Create a project estimate form.",
  },
  {
    displayText: "Publish quarterly report",
    prompt: "Publish the quarterly revenue report for executive leadership.",
  },
];

export default function App() {
  const llm = useMemo(() => createAgentFrameworkLLM(`${BACKEND_URL}/agent`), []);

  return (
    <main className="app-shell" data-testid="openui-agent-shell">
      <AgentInterface
        llm={llm}
        componentLibrary={library}
        theme={microsoftTheme}
        agentName="Agent Framework + OpenUI"
        starters={starters}
        starterVariant="long"
        scrollVariant="always"
      />
    </main>
  );
}
