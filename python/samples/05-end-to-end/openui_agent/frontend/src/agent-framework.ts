// Copyright (c) Microsoft. All rights reserved.

import {
  EventType,
  agUIAdapter,
  type AGUIEvent,
  type ChatLLM,
  type Message,
  type StreamProtocolAdapter,
} from "@openuidev/react-ui";

export interface AgentFrameworkInterrupt {
  id: string;
  reason?: string;
  message?: string;
  toolCallId?: string;
  responseSchema?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

interface AgentFrameworkRunRequest {
  threadId: string;
  runId: string;
  messages: Message[];
  availableInterrupts?: AgentFrameworkInterrupt[];
  resume?: Array<{
    interruptId: string;
    status: "resolved";
    payload: { approved: boolean };
  }>;
}

const pendingInterrupts = new Map<string, AgentFrameworkInterrupt[]>();
const APPROVE_ACTION = "Approve and publish report";
const REJECT_ACTION = "Reject report publication";
const CONTENT_MARKER = "]]>openui:content\n";
const CONTEXT_MARKER = "\n]]>openui:context\n";

function randomId(): string {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `id-${Math.random().toString(16).slice(2)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asInterrupts(value: unknown): AgentFrameworkInterrupt[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) =>
    isRecord(item) && typeof item.id === "string" && item.id.length > 0
      ? [{ ...item, id: item.id } as AgentFrameworkInterrupt]
      : [],
  );
}

export function extractInterrupts(event: unknown): AgentFrameworkInterrupt[] {
  if (!isRecord(event)) {
    return [];
  }

  const outcome = event.outcome;
  if (isRecord(outcome)) {
    const canonical = asInterrupts(outcome.interrupts);
    if (canonical.length > 0) {
      return canonical;
    }
  }

  return asInterrupts(event.interrupts ?? event.interrupt);
}

function isContinueAction(content: string, label: string): boolean {
  const contextIndex = content.indexOf(CONTEXT_MARKER);
  if (contextIndex === -1 || content.slice(0, contextIndex) !== `${CONTENT_MARKER}${label}`) {
    return false;
  }

  try {
    const context = JSON.parse(content.slice(contextIndex + CONTEXT_MARKER.length)) as unknown;
    return Array.isArray(context) && context[0] === `User clicked: ${label}`;
  } catch {
    return false;
  }
}

function approvalDecision(messages: Message[]): boolean | null {
  const latest = messages.at(-1);
  if (latest?.role !== "user" || typeof latest.content !== "string") {
    return null;
  }
  if (isContinueAction(latest.content, APPROVE_ACTION)) {
    return true;
  }
  if (isContinueAction(latest.content, REJECT_ACTION)) {
    return false;
  }
  return null;
}

export function buildAgentFrameworkRequest(
  threadId: string,
  messages: Message[],
  interrupts: AgentFrameworkInterrupt[] = [],
): AgentFrameworkRunRequest {
  const decision = interrupts.length > 0 ? approvalDecision(messages) : null;
  if (decision !== null) {
    return {
      threadId,
      runId: randomId(),
      messages: [],
      availableInterrupts: interrupts,
      resume: interrupts.map((interrupt) => ({
        interruptId: interrupt.id,
        status: "resolved",
        payload: { approved: decision },
      })),
    };
  }

  return {
    threadId,
    runId: randomId(),
    // Agent Framework's snapshot store owns history, so send only the new turn.
    messages: messages.slice(-1),
  };
}

interface InterruptDetails {
  toolName: string;
  arguments: Record<string, unknown>;
  argumentsText: string;
}

function interruptDetails(interrupt: AgentFrameworkInterrupt): InterruptDetails {
  const agentFramework = isRecord(interrupt.metadata?.agent_framework)
    ? interrupt.metadata.agent_framework
    : undefined;
  const functionCall = isRecord(agentFramework?.function_call) ? agentFramework.function_call : undefined;
  const toolName = typeof functionCall?.name === "string" ? functionCall.name : "Agent Framework tool";
  const args = isRecord(functionCall?.arguments) ? functionCall.arguments : {};
  const argumentsText = Object.keys(args).length > 0 ? JSON.stringify(args) : "No arguments were supplied.";
  return { toolName, arguments: args, argumentsText };
}

function stringArgument(args: Record<string, unknown>, name: string, fallback: string): string {
  return typeof args[name] === "string" && args[name].length > 0 ? args[name] : fallback;
}

function revenueArguments(args: Record<string, unknown>): number[] | null {
  const values = ["q1_revenue", "q2_revenue", "q3_revenue", "q4_revenue"].map((name) => args[name]);
  return values.every((value) => typeof value === "number" && Number.isFinite(value))
    ? (values as number[])
    : null;
}

export function approvalCard(interrupt: AgentFrameworkInterrupt): string {
  const { toolName, arguments: args, argumentsText } = interruptDetails(interrupt);
  const title = stringArgument(args, "title", "Untitled report");
  const audience = stringArgument(args, "audience", "Unspecified audience");
  const revenue = revenueArguments(args);

  if (toolName === "publish_revenue_report" && revenue) {
    const total = revenue.reduce((sum, value) => sum + value, 0);
    const strongestIndex = revenue.indexOf(Math.max(...revenue));
    const strongestQuarter = ["Q1", "Q2", "Q3", "Q4"][strongestIndex];

    return [
      "root = Card([header, status, chart, details, reviewSteps, actions])",
      `header = CardHeader("Revenue release review", ${JSON.stringify(title)})`,
      `status = Callout("warning", "Awaiting your decision", ${JSON.stringify(
        "Nothing has been published. Review the figures and choose whether Agent Framework may run the publishing tool.",
      )})`,
      'chart = BarChart(labels, [revenue], "grouped", "Quarter", "Revenue ($K)")',
      'labels = ["Q1", "Q2", "Q3", "Q4"]',
      `revenue = Series("Revenue ($K)", ${JSON.stringify(revenue)})`,
      "details = Table([detailNames, detailValues])",
      'detailNames = Col("Review detail", ["Audience", "Total revenue", "Strongest quarter"])',
      `detailValues = Col("Value", ${JSON.stringify([audience, `$${total}K`, strongestQuarter])})`,
      "reviewSteps = Steps([prepared, decision, publish])",
      'prepared = StepsItem("1. Data prepared", "Quarterly figures came from get_quarterly_revenue.")',
      'decision = StepsItem("2. Human decision", "Approve or reject this exact release below.")',
      'publish = StepsItem("3. Publish", "publish_revenue_report runs only after approval.")',
      "actions = FollowUpBlock([approve, reject])",
      `approve = FollowUpItem(${JSON.stringify(APPROVE_ACTION)})`,
      `reject = FollowUpItem(${JSON.stringify(REJECT_ACTION)})`,
    ].join("\n");
  }

  return [
    "root = Card([header, status, details, actions])",
    'header = CardHeader("Tool approval required", "Agent Framework paused before execution")',
    `status = Callout("warning", ${JSON.stringify(toolName)}, "Nothing has run yet.")`,
    "details = Table([detailNames, detailValues])",
    'detailNames = Col("Review detail", ["Request", "Arguments"])',
    `detailValues = Col("Value", ${JSON.stringify([interrupt.message ?? "Approval requested", argumentsText])})`,
    "actions = FollowUpBlock([approve, reject])",
    `approve = FollowUpItem(${JSON.stringify(APPROVE_ACTION)})`,
    `reject = FollowUpItem(${JSON.stringify(REJECT_ACTION)})`,
  ].join("\n");
}

export function agentFrameworkStreamAdapter(): StreamProtocolAdapter {
  const baseAdapter = agUIAdapter();

  return {
    async *parse(response: Response): AsyncIterable<AGUIEvent> {
      let activeThreadId: string | null = null;

      for await (const event of baseAdapter.parse(response)) {
        const record = event as unknown as Record<string, unknown>;
        if (typeof record.threadId === "string") {
          activeThreadId = record.threadId;
        }

        if (event.type === EventType.RUN_FINISHED) {
          const interrupts = extractInterrupts(record);
          if (activeThreadId && interrupts.length > 0) {
            pendingInterrupts.set(activeThreadId, interrupts);
            const messageId = randomId();
            yield { type: EventType.TEXT_MESSAGE_START, messageId } as AGUIEvent;
            yield {
              type: EventType.TEXT_MESSAGE_CONTENT,
              messageId,
              delta: approvalCard(interrupts[0]),
            } as AGUIEvent;
            yield { type: EventType.TEXT_MESSAGE_END, messageId } as AGUIEvent;
          } else if (activeThreadId) {
            pendingInterrupts.delete(activeThreadId);
          }
        }

        yield event;
      }
    },
  };
}

export function createAgentFrameworkLLM(endpoint: string): ChatLLM {
  return {
    streamProtocol: agentFrameworkStreamAdapter(),
    async send({ threadId, messages, signal }): Promise<Response> {
      const interrupts = pendingInterrupts.get(threadId) ?? [];
      const request = buildAgentFrameworkRequest(threadId, messages, interrupts);
      const isResume = request.resume !== undefined;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
        signal,
      });

      if (!response.ok) {
        throw new Error(`Agent Framework request failed with status ${response.status}.`);
      }
      if (isResume) {
        pendingInterrupts.delete(threadId);
      }
      return response;
    },
  };
}
