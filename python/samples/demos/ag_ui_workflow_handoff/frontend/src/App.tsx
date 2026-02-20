// Copyright (c) Microsoft. All rights reserved.

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type AgUiEvent = Record<string, unknown> & { type: string };

type AgentId = "triage_agent" | "refund_agent" | "order_agent";

interface Interrupt {
  id: string;
  value: unknown;
}

interface RequestInfoPayload {
  request_id?: string;
  source_executor_id?: string;
  request_type?: string;
  response_type?: string;
  data?: unknown;
}

interface DisplayMessage {
  id: string;
  role: "assistant" | "user" | "system";
  text: string;
}

interface CaseSnapshot {
  orderId: string;
  refundAmount: string;
  refundApproved: "pending" | "approved" | "rejected";
  shippingPreference: string;
}

interface UsageDiagnostics {
  runId: string;
  inputTokenCount?: number;
  outputTokenCount?: number;
  totalTokenCount?: number;
  recordedAt: number;
  raw: Record<string, unknown>;
}

const KNOWN_AGENTS: AgentId[] = ["triage_agent", "refund_agent", "order_agent"];

const AGENT_LABELS: Record<AgentId, string> = {
  triage_agent: "Triage",
  refund_agent: "Refund",
  order_agent: "Order",
};

const STARTER_PROMPTS = [
  "My order 12345 arrived damaged and I need a refund.",
  "Help me with a damaged-order refund and replacement.",
];

function randomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Math.random().toString(16).slice(2)}`;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function getValue(source: Record<string, unknown>, ...keys: string[]): unknown {
  for (const key of keys) {
    if (key in source) {
      return source[key];
    }
  }
  return undefined;
}

function getString(source: Record<string, unknown>, ...keys: string[]): string | undefined {
  const value = getValue(source, ...keys);
  return typeof value === "string" ? value : undefined;
}

function getObject(source: Record<string, unknown>, ...keys: string[]): Record<string, unknown> | undefined {
  const value = getValue(source, ...keys);
  return isObject(value) ? value : undefined;
}

function safeParseJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function extractTextFromMessagePayload(messagePayload: unknown): string {
  if (!isObject(messagePayload)) {
    return "";
  }

  const directText = getString(messagePayload, "text", "content");
  if (directText && directText.length > 0) {
    return directText;
  }

  const contentItems = getValue(messagePayload, "contents", "content");
  if (Array.isArray(contentItems)) {
    const pieces: string[] = [];
    for (const content of contentItems) {
      if (!isObject(content)) {
        continue;
      }
      if (content.type !== "text") {
        continue;
      }
      const text = getString(content, "text", "content");
      if (text) {
        pieces.push(text);
      }
    }
    return pieces.join(" ").trim();
  }

  return "";
}

function extractPromptFromInterrupt(interrupt: Interrupt, payload?: RequestInfoPayload): string {
  const interruptValue = interrupt.value;
  if (!isObject(interruptValue)) {
    return "Provide the requested information to continue.";
  }

  const directPrompt = getString(interruptValue, "message", "prompt");
  if (directPrompt && directPrompt.length > 0) {
    return directPrompt;
  }

  if (payload && isObject(payload.data)) {
    const agentResponse = getObject(payload.data, "agent_response", "agentResponse");
    if (agentResponse && Array.isArray(agentResponse.messages)) {
      const texts = agentResponse.messages
        .map((message) => extractTextFromMessagePayload(message))
        .filter((text) => text.length > 0);
      if (texts.length > 0) {
        return texts.join(" ");
      }
    }
  }

  const interruptAgentResponse = getObject(interruptValue, "agent_response", "agentResponse");
  if (interruptAgentResponse && Array.isArray(interruptAgentResponse.messages)) {
    const texts = interruptAgentResponse.messages
      .map((message) => extractTextFromMessagePayload(message))
      .filter((text) => text.length > 0);
    if (texts.length > 0) {
      return texts.join(" ");
    }
  }

  return "Provide the requested information to continue.";
}

function extractFunctionCallFromInterrupt(interrupt: Interrupt): Record<string, unknown> | null {
  if (!isObject(interrupt.value)) {
    return null;
  }

  const maybeCall = getObject(interrupt.value, "function_call", "functionCall");
  if (isObject(maybeCall)) {
    return maybeCall;
  }
  return null;
}

function parseFunctionArguments(functionCall: Record<string, unknown> | null): Record<string, unknown> {
  if (!functionCall) {
    return {};
  }

  const rawArguments = functionCall.arguments;
  if (isObject(rawArguments)) {
    return rawArguments;
  }
  if (typeof rawArguments === "string") {
    const parsed = safeParseJson(rawArguments);
    if (isObject(parsed)) {
      return parsed;
    }
  }
  return {};
}

function interruptKind(interrupt: Interrupt): "approval" | "handoff_input" | "unknown" {
  if (isObject(interrupt.value) && getString(interrupt.value, "type") === "function_approval_request") {
    return "approval";
  }
  if (isObject(interrupt.value) && getObject(interrupt.value, "agent_response", "agentResponse")) {
    return "handoff_input";
  }
  if (isObject(interrupt.value) && getString(interrupt.value, "message", "prompt")) {
    return "handoff_input";
  }
  return "unknown";
}

function normalizeRole(role: unknown): "assistant" | "user" | "system" {
  if (role === "user" || role === "assistant" || role === "system") {
    return role;
  }
  return "assistant";
}

function normalizeTextForDedupe(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function normalizeShippingPreference(text: string): string | null {
  const normalized = text.trim().toLowerCase();
  if (normalized.length === 0) {
    return null;
  }

  if (/\bstandard\b/.test(normalized)) {
    return "standard";
  }

  if (/\b(expedited|express|overnight|priority|next[-\s]?day)\b/.test(normalized)) {
    return "expedited";
  }

  return null;
}

function getFiniteNumber(value: unknown): number | undefined {
  if (typeof value !== "number") {
    return undefined;
  }
  if (!Number.isFinite(value)) {
    return undefined;
  }
  return value;
}

function normalizeUsagePayload(value: unknown, runId: string | null): UsageDiagnostics | null {
  if (!isObject(value)) {
    return null;
  }

  return {
    runId: runId ?? "unknown",
    inputTokenCount: getFiniteNumber(value.input_token_count),
    outputTokenCount: getFiniteNumber(value.output_token_count),
    totalTokenCount: getFiniteNumber(value.total_token_count),
    recordedAt: Date.now(),
    raw: value,
  };
}

export default function App(): JSX.Element {
  const backendUrl = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8891";
  const endpoint = `${backendUrl.replace(/\/$/, "")}/handoff_demo`;

  const threadIdRef = useRef<string>(randomId());
  const assistantMessageIndexRef = useRef<Record<string, number>>({});
  const activeRunIdRef = useRef<string | null>(null);
  const pendingUsageRef = useRef<UsageDiagnostics | null>(null);

  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [requestInfoById, setRequestInfoById] = useState<Record<string, RequestInfoPayload>>({});
  const [pendingInterrupts, setPendingInterrupts] = useState<Interrupt[]>([]);
  const [activeAgent, setActiveAgent] = useState<AgentId>("triage_agent");
  const [visitedAgents, setVisitedAgents] = useState<Set<AgentId>>(new Set(["triage_agent"]));
  const [caseSnapshot, setCaseSnapshot] = useState<CaseSnapshot>({
    orderId: "Not captured",
    refundAmount: "Not captured",
    refundApproved: "pending",
    shippingPreference: "Not selected",
  });
  const [statusText, setStatusText] = useState<string>("Ready");
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [inputText, setInputText] = useState<string>("");
  const [isApprovalModalOpen, setIsApprovalModalOpen] = useState<boolean>(false);
  const [latestUsage, setLatestUsage] = useState<UsageDiagnostics | null>(null);
  const [usageHistory, setUsageHistory] = useState<UsageDiagnostics[]>([]);

  const currentInterrupt = pendingInterrupts[0];
  const currentInterruptKind = currentInterrupt ? interruptKind(currentInterrupt) : "unknown";
  const currentRequestInfo = currentInterrupt ? requestInfoById[currentInterrupt.id] : undefined;
  const interruptPrompt = currentInterrupt
    ? extractPromptFromInterrupt(currentInterrupt, currentRequestInfo)
    : "No pending interrupt.";

  const functionCall = currentInterrupt ? extractFunctionCallFromInterrupt(currentInterrupt) : null;
  const functionArguments = useMemo(() => parseFunctionArguments(functionCall), [functionCall]);

  useEffect(() => {
    if (currentInterruptKind === "approval") {
      setIsApprovalModalOpen(true);
      return;
    }
    setIsApprovalModalOpen(false);
  }, [currentInterruptKind, currentInterrupt?.id]);

  const pushMessage = (message: DisplayMessage): void => {
    setMessages((prev) => [...prev, message]);
  };

  const rebuildAssistantMessageIndex = (items: DisplayMessage[]): void => {
    const next: Record<string, number> = {};
    items.forEach((item, index) => {
      if (item.role === "assistant") {
        next[item.id] = index;
      }
    });
    assistantMessageIndexRef.current = next;
  };

  const upsertAssistantStart = (messageId: string, role: unknown): void => {
    const normalizedRole = normalizeRole(role);
    if (normalizedRole === "user") {
      return;
    }

    setMessages((prev) => {
      const existingIndex = prev.findIndex((item) => item.id === messageId);
      if (existingIndex >= 0) {
        return prev;
      }
      const next: DisplayMessage[] = [...prev, { id: messageId, role: normalizedRole, text: "" }];
      rebuildAssistantMessageIndex(next);
      return next;
    });
  };

  const appendAssistantDelta = (messageId: string, delta: string): void => {
    setMessages((prev) => {
      const index = assistantMessageIndexRef.current[messageId];
      if (index === undefined) {
        const next: DisplayMessage[] = [...prev, { id: messageId, role: "assistant", text: delta }];
        rebuildAssistantMessageIndex(next);
        return next;
      }

      const next = [...prev];
      const existing = next[index];
      const existingCanonical = normalizeTextForDedupe(existing.text);
      const deltaCanonical = normalizeTextForDedupe(delta);
      if (
        existingCanonical.length >= 24 &&
        deltaCanonical.length >= 24 &&
        existingCanonical === deltaCanonical
      ) {
        return prev;
      }
      next[index] = { ...existing, text: `${existing.text}${delta}` };
      return next;
    });
  };

  const finalizeAssistantMessage = (messageId: string): void => {
    setMessages((prev) => {
      const index = assistantMessageIndexRef.current[messageId];
      if (index === undefined) {
        return prev;
      }
      const candidate = prev[index];
      if (candidate.role === "user" || candidate.text.trim().length > 0) {
        return prev;
      }
      const next = prev.filter((item) => item.id !== messageId);
      rebuildAssistantMessageIndex(next);
      return next;
    });
  };

  const updateCaseFromApprovalRequest = (payload: RequestInfoPayload): void => {
    if (!isObject(payload.data) || getString(payload.data, "type") !== "function_approval_request") {
      return;
    }
    const functionCallPayload = getObject(payload.data, "function_call", "functionCall") ?? null;
    const functionName = functionCallPayload ? getString(functionCallPayload, "name") : undefined;
    const args = parseFunctionArguments(functionCallPayload);
    const replacementShippingPreference = getString(args, "shipping_preference", "shippingPreference");

    setCaseSnapshot((prev) => ({
      ...prev,
      orderId: getString(args, "order_id", "orderId") ?? prev.orderId,
      refundAmount: getString(args, "amount") ?? prev.refundAmount,
      shippingPreference: replacementShippingPreference ?? prev.shippingPreference,
      refundApproved: functionName === "submit_refund" ? "pending" : prev.refundApproved,
    }));
  };

  const updateActiveAgent = (candidate: unknown): void => {
    if (candidate !== "triage_agent" && candidate !== "refund_agent" && candidate !== "order_agent") {
      return;
    }

    setActiveAgent(candidate);
    setVisitedAgents((prev) => {
      const next = new Set(prev);
      next.add(candidate);
      return next;
    });
  };

  const handleEvent = (event: AgUiEvent): void => {
    switch (event.type) {
      case "RUN_STARTED":
        if (isObject(event)) {
          const runId = getString(event, "run_id", "runId");
          if (runId) {
            activeRunIdRef.current = runId;
          }
        }
        setStatusText("Run started");
        break;
      case "STEP_STARTED":
        if (isObject(event)) {
          const stepName = getString(event, "step_name", "stepName", "name");
          if (stepName) {
            updateActiveAgent(stepName);
            setStatusText(`Running ${stepName}`);
          }
        }
        break;
      case "TEXT_MESSAGE_START":
        if (isObject(event)) {
          const messageId = getString(event, "message_id", "messageId");
          if (messageId) {
            upsertAssistantStart(messageId, event.role);
          }
        }
        break;
      case "TEXT_MESSAGE_CONTENT":
        if (isObject(event)) {
          const messageId = getString(event, "message_id", "messageId");
          const delta = getString(event, "delta");
          if (messageId && delta) {
            appendAssistantDelta(messageId, delta);
          }
        }
        break;
      case "TEXT_MESSAGE_END":
        if (isObject(event)) {
          const messageId = getString(event, "message_id", "messageId");
          if (messageId) {
            finalizeAssistantMessage(messageId);
          }
        }
        break;
      case "MESSAGES_SNAPSHOT":
        // Intentionally ignored for chat rendering in this demo.
        // AG-UI snapshots can contain full conversation history and cause replay duplication.
        break;
      case "TOOL_CALL_ARGS": {
        if (!isObject(event)) {
          break;
        }

        const toolCallId = getString(event, "tool_call_id", "toolCallId");
        const deltaRaw = getValue(event, "delta");
        if (!toolCallId) {
          break;
        }

        const parsed =
          typeof deltaRaw === "string"
            ? safeParseJson(deltaRaw)
            : isObject(deltaRaw)
              ? deltaRaw
              : null;
        if (!isObject(parsed)) {
          break;
        }

        const payload: RequestInfoPayload = {
          request_id: getString(parsed, "request_id", "requestId"),
          source_executor_id: getString(parsed, "source_executor_id", "sourceExecutorId"),
          request_type: getString(parsed, "request_type", "requestType"),
          response_type: getString(parsed, "response_type", "responseType"),
          data: getValue(parsed, "data"),
        };

        setRequestInfoById((prev) => ({
          ...prev,
          [toolCallId]: payload,
        }));

        updateCaseFromApprovalRequest(payload);
        updateActiveAgent(payload.source_executor_id);
        break;
      }
      case "TOOL_CALL_RESULT":
        if (isObject(event)) {
          const rawContent = getValue(event, "content");
          const parsed =
            typeof rawContent === "string"
              ? safeParseJson(rawContent)
              : isObject(rawContent)
                ? rawContent
                : null;
          if (isObject(parsed)) {
            updateActiveAgent(getString(parsed, "handoff_to", "handoffTo"));
          }
        }
        break;
      case "CUSTOM":
        if (isObject(event) && getString(event, "name") === "usage") {
          const usage = normalizeUsagePayload(getValue(event, "value"), activeRunIdRef.current);
          if (usage) {
            pendingUsageRef.current = usage;
          }
        }
        break;
      case "RUN_ERROR":
        setMessages((prev) => {
          const text = `Run error: ${isObject(event) ? (getString(event, "message") ?? "Unknown error") : "Unknown error"}`;
          if (prev.length > 0 && prev[prev.length - 1]?.role === "system" && prev[prev.length - 1]?.text === text) {
            return prev;
          }
          return [...prev, { id: randomId(), role: "system", text }];
        });
        setStatusText("Run failed");
        setIsRunning(false);
        pendingUsageRef.current = null;
        break;
      case "RUN_FINISHED": {
        const usage = pendingUsageRef.current;
        if (usage) {
          setLatestUsage(usage);
          setUsageHistory((prev) => [usage, ...prev].slice(0, 6));
          pendingUsageRef.current = null;
        }

        const rawInterrupts = isObject(event) ? getValue(event, "interrupt", "interrupts") : undefined;
        const interruptPayload = Array.isArray(rawInterrupts)
          ? rawInterrupts
              .filter((item): item is Record<string, unknown> => isObject(item))
              .map((item) => ({
                id: String(item.id ?? ""),
                value: item.value,
              }))
              .filter((item) => item.id.length > 0)
          : [];

        for (const interrupt of interruptPayload) {
          if (!isObject(interrupt.value)) {
            continue;
          }

          updateCaseFromApprovalRequest({ data: interrupt.value });

          const sourceExecutor = getString(interrupt.value, "source_executor_id", "sourceExecutorId");
          if (sourceExecutor) {
            updateActiveAgent(sourceExecutor);
          }

          const agentResponse = getObject(interrupt.value, "agent_response", "agentResponse");
          if (agentResponse && Array.isArray(agentResponse.messages)) {
            const lastMessage = [...agentResponse.messages].reverse().find(isObject);
            if (lastMessage) {
              updateActiveAgent(getString(lastMessage, "author_name", "authorName"));
            }
          }
        }

        setPendingInterrupts(interruptPayload);
        setStatusText(interruptPayload.length > 0 ? "Waiting for input" : "Run complete");
        setIsRunning(false);
        break;
      }
      default:
        break;
    }
  };

  const streamRun = async (body: Record<string, unknown>): Promise<void> => {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Request failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    const processSseChunk = (rawChunk: string): void => {
      const dataLines = rawChunk
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim());

      if (dataLines.length === 0) {
        return;
      }

      const payload = dataLines.join("\n");
      const parsed = safeParseJson(payload);
      if (isObject(parsed) && typeof parsed.type === "string") {
        handleEvent(parsed as AgUiEvent);
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      while (true) {
        const boundaryIndex = buffer.indexOf("\n\n");
        if (boundaryIndex < 0) {
          break;
        }

        const rawEvent = buffer.slice(0, boundaryIndex);
        buffer = buffer.slice(boundaryIndex + 2);
        processSseChunk(rawEvent);
      }
    }

    const tail = buffer.trim();
    if (tail.length > 0) {
      processSseChunk(tail);
    }
  };

  const runWithPayload = async (payload: Record<string, unknown>): Promise<void> => {
    activeRunIdRef.current = typeof payload.run_id === "string" ? payload.run_id : null;
    pendingUsageRef.current = null;
    setIsRunning(true);
    setStatusText("Connecting");

    try {
      await streamRun(payload);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      pushMessage({ id: randomId(), role: "system", text: `Network error: ${message}` });
      setStatusText("Network error");
      setIsRunning(false);
    }
  };

  const startNewTurn = async (text: string): Promise<void> => {
    pushMessage({ id: randomId(), role: "user", text });

    await runWithPayload({
      thread_id: threadIdRef.current,
      run_id: randomId(),
      messages: [{ role: "user", content: text }],
    });
  };

  const resumeApproval = async (approved: boolean): Promise<void> => {
    if (!currentInterrupt || !functionCall) {
      return;
    }

    const functionName = getString(functionCall, "name") ?? "tool_call";

    if (functionName === "submit_refund") {
      setCaseSnapshot((prev) => ({
        ...prev,
        refundApproved: approved ? "approved" : "rejected",
      }));
    }

    setIsApprovalModalOpen(false);

    pushMessage({
      id: randomId(),
      role: "system",
      text: approved ? `HITL Reviewer approved ${functionName}.` : `HITL Reviewer rejected ${functionName}.`,
    });

    const approvalResponse = {
      type: "function_approval_response",
      approved,
      id: String((isObject(currentInterrupt.value) && currentInterrupt.value.id) || currentInterrupt.id),
      function_call: functionCall,
    };

    await runWithPayload({
      thread_id: threadIdRef.current,
      run_id: randomId(),
      messages: [],
      resume: {
        interrupts: [
          {
            id: currentInterrupt.id,
            value: approvalResponse,
          },
        ],
      },
    });
  };

  const resumeHandoffInput = async (text: string): Promise<void> => {
    if (!currentInterrupt) {
      return;
    }

    const fromOrderAgent = currentRequestInfo?.source_executor_id === "order_agent";
    const shippingPreference = fromOrderAgent ? normalizeShippingPreference(text) : null;
    if (shippingPreference) {
      setCaseSnapshot((prev) => ({
        ...prev,
        shippingPreference,
      }));
    }

    pushMessage({ id: randomId(), role: "user", text });

    await runWithPayload({
      thread_id: threadIdRef.current,
      run_id: randomId(),
      messages: [],
      resume: {
        interrupts: [
          {
            id: currentInterrupt.id,
            value: [
              {
                role: "user",
                contents: [{ type: "text", text }],
              },
            ],
          },
        ],
      },
    });
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const trimmed = inputText.trim();
    if (!trimmed || isRunning) {
      return;
    }

    setInputText("");

    if (currentInterruptKind === "approval") {
      setIsApprovalModalOpen(true);
      return;
    }

    if (currentInterruptKind === "handoff_input") {
      await resumeHandoffInput(trimmed);
      return;
    }

    await startNewTurn(trimmed);
  };

  return (
    <div className="page-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">AG-UI Workflow Demo</p>
          <h1>Handoff + Tool Approval</h1>
          <p className="subtitle">
            Dynamic workflow exercising AG-UI run events, interrupt resumes, function approvals, and stateful
            per-thread execution.
          </p>
        </div>
        <div className="status-pill" data-running={isRunning}>
          <span>Status</span>
          <strong>{statusText}</strong>
        </div>
      </header>

      <div className="layout">
        <section className="dashboard-panel">
          <article className="card snapshot-card">
            <h2>Case Snapshot</h2>
            <div className="snapshot-grid">
              <div>
                <span>Order ID</span>
                <strong>{caseSnapshot.orderId}</strong>
              </div>
              <div>
                <span>Refund Amount</span>
                <strong>{caseSnapshot.refundAmount}</strong>
              </div>
              <div>
                <span>Refund Approval</span>
                <strong data-state={caseSnapshot.refundApproved}>{caseSnapshot.refundApproved}</strong>
              </div>
              <div>
                <span>Shipping Preference</span>
                <strong>{caseSnapshot.shippingPreference}</strong>
              </div>
            </div>
          </article>

          <article className="card agents-card">
            <h2>Active Agent</h2>
            <div className="agent-pills">
              {KNOWN_AGENTS.map((agent) => (
                <button
                  key={agent}
                  type="button"
                  className="agent-pill"
                  data-active={agent === activeAgent}
                  data-seen={visitedAgents.has(agent)}
                  disabled
                >
                  {AGENT_LABELS[agent]}
                </button>
              ))}
            </div>
          </article>

          <article className="card diagnostics-card">
            <h2>Diagnostics</h2>
            {!latestUsage && <p className="muted">Usage appears when the final streaming chunk arrives.</p>}

            {latestUsage && (
              <div className="diagnostics-body">
                <div className="diagnostics-grid">
                  <div>
                    <span>Run ID</span>
                    <strong>{latestUsage.runId}</strong>
                  </div>
                  <div>
                    <span>Input Tokens</span>
                    <strong>{latestUsage.inputTokenCount ?? "n/a"}</strong>
                  </div>
                  <div>
                    <span>Output Tokens</span>
                    <strong>{latestUsage.outputTokenCount ?? "n/a"}</strong>
                  </div>
                  <div>
                    <span>Total Tokens</span>
                    <strong>{latestUsage.totalTokenCount ?? "n/a"}</strong>
                  </div>
                </div>

                <p className="muted diagnostics-timestamp">
                  Last updated {new Date(latestUsage.recordedAt).toLocaleTimeString()}
                </p>

                <details className="diagnostics-raw">
                  <summary>Raw usage payload</summary>
                  <pre>{JSON.stringify(latestUsage.raw, null, 2)}</pre>
                </details>

                {usageHistory.length > 1 && (
                  <div className="diagnostics-history">
                    <h3>Recent runs</h3>
                    {usageHistory.map((entry, index) => (
                      <div key={`${entry.runId}-${entry.recordedAt}-${index}`} className="diagnostics-history-item">
                        <span>{entry.runId}</span>
                        <strong>{entry.totalTokenCount ?? "n/a"} total</strong>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </article>

          <article className="card interrupt-card">
            <h2>Pending Action</h2>
            {!currentInterrupt && <p className="muted">No interrupt pending. Start with one of the prompts below.</p>}

            {currentInterrupt && (
              <div className="interrupt-body">
                <p>{interruptPrompt}</p>

                {currentInterruptKind === "approval" && (
                  <div className="approval-inline">
                    <p className="muted">
                      Customer input is paused. A separate reviewer must approve or reject this tool call.
                    </p>
                    <div className="approval-details">
                      <p>
                        <strong>Function:</strong> {String(functionCall?.name ?? "tool_call")}
                      </p>
                      <pre>{JSON.stringify(functionArguments, null, 2)}</pre>
                    </div>
                    <button
                      type="button"
                      className="approval-launch"
                      onClick={() => setIsApprovalModalOpen(true)}
                      disabled={isRunning}
                    >
                      Open Reviewer Modal
                    </button>
                  </div>
                )}

                {currentInterruptKind === "handoff_input" && (
                  <p className="muted">Reply in the chat input to resume this request.</p>
                )}
              </div>
            )}

            {!currentInterrupt && (
              <div className="starter-prompts">
                {STARTER_PROMPTS.map((prompt) => (
                  <button key={prompt} type="button" onClick={() => void startNewTurn(prompt)} disabled={isRunning}>
                    {prompt}
                  </button>
                ))}
              </div>
            )}
          </article>
        </section>

        <section className="chat-panel">
          <div className="chat-scroll">
            {messages.length === 0 && (
              <div className="empty-state">
                <p>Send a message to start the handoff workflow.</p>
              </div>
            )}

            {messages.map((message) => (
              <article key={message.id} className="chat-bubble" data-role={message.role}>
                <header>{message.role}</header>
                <p>{message.text}</p>
              </article>
            ))}
          </div>

          <form className="chat-input" onSubmit={(event) => void handleSubmit(event)}>
            <input
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              placeholder={
                currentInterruptKind === "approval"
                  ? "Waiting for reviewer approval..."
                  : currentInterruptKind === "handoff_input"
                    ? "Reply to continue..."
                    : "Describe your issue..."
              }
              disabled={isRunning || currentInterruptKind === "approval"}
            />
            <button type="submit" disabled={isRunning || currentInterruptKind === "approval" || inputText.trim().length === 0}>
              Send
            </button>
          </form>
        </section>
      </div>

      {currentInterruptKind === "approval" && currentInterrupt && isApprovalModalOpen && (
        <div className="approval-modal-backdrop" onClick={() => setIsApprovalModalOpen(false)}>
          <section className="approval-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <header className="approval-modal-header">
              <div>
                <p className="approval-modal-label">HITL Reviewer Console</p>
                <h3>Tool Approval Required</h3>
              </div>
              <button type="button" className="approval-modal-close" onClick={() => setIsApprovalModalOpen(false)}>
                Close
              </button>
            </header>

            <p className="muted">{interruptPrompt}</p>

            <div className="approval-details">
              <p>
                <strong>Function:</strong> {String(functionCall?.name ?? "tool_call")}
              </p>
              <pre>{JSON.stringify(functionArguments, null, 2)}</pre>
            </div>

            <div className="approval-actions">
              <button type="button" className="defer" onClick={() => setIsApprovalModalOpen(false)} disabled={isRunning}>
                Defer
              </button>
              <button type="button" className="reject" onClick={() => void resumeApproval(false)} disabled={isRunning}>
                Reject Tool Call
              </button>
              <button type="button" className="approve" onClick={() => void resumeApproval(true)} disabled={isRunning}>
                Approve Tool Call
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
