// Copyright (c) Microsoft. All rights reserved.

import { describe, expect, it } from "vitest";
import { EventType, type Message } from "@openuidev/react-ui";

import {
  agentFrameworkStreamAdapter,
  buildAgentFrameworkRequest,
  extractInterrupts,
  type AgentFrameworkInterrupt,
} from "./agent-framework";

function userMessage(content: string, id: string): Message {
  return { id, role: "user", content };
}

function actionMessage(label: string, formState?: Record<string, string>): string {
  const context: Array<string | Record<string, string>> = [`User clicked: ${label}`];
  if (formState) {
    context.push(formState);
  }
  return `]]>openui:content\n${label}\n]]>openui:context\n${JSON.stringify(context)}`;
}

const approvalInterrupt: AgentFrameworkInterrupt = {
  id: "approval-17",
  reason: "tool_call",
  message: "Approve running publish_revenue_report?",
  toolCallId: "call-17",
  metadata: {
    agent_framework: {
      function_call: {
        name: "publish_revenue_report",
        arguments: {
          title: "FY26 Quarterly Revenue Pulse",
          audience: "Executive leadership team",
          q1_revenue: 120,
          q2_revenue: 180,
          q3_revenue: 150,
          q4_revenue: 240,
        },
      },
    },
  },
};

describe("Agent Framework transport", () => {
  it("sends only the latest turn because Agent Framework owns thread history", () => {
    const request = buildAgentFrameworkRequest("thread-1", [
      userMessage("Older turn", "message-1"),
      userMessage("Compare the strongest and weakest quarter", "message-2"),
    ]);

    expect(request.threadId).toBe("thread-1");
    expect(request.messages).toEqual([userMessage("Compare the strongest and weakest quarter", "message-2")]);
    expect(request.resume).toBeUndefined();
  });

  it("keeps form values and action context in the outgoing LLM turn", () => {
    const formAction = actionMessage("Submit the project estimate", {
      projectName: "Aurora-731",
      teamSize: "7",
      notes: "Prioritize accessibility and charts",
    });

    const request = buildAgentFrameworkRequest("thread-form", [userMessage(formAction, "message-form")]);
    expect(JSON.stringify(request.messages)).toContain("Aurora-731");
    expect(JSON.stringify(request.messages)).toContain("teamSize");
    expect(JSON.stringify(request.messages)).toContain("Prioritize accessibility and charts");
  });

  it("maps an OpenUI approval follow-up to the canonical AG-UI resume request", () => {
    const request = buildAgentFrameworkRequest(
      "thread-approval",
      [userMessage(actionMessage("Approve and publish report"), "message-approval")],
      [approvalInterrupt],
    );

    expect(request.messages).toEqual([]);
    expect(request.availableInterrupts).toEqual([approvalInterrupt]);
    expect(request.resume).toEqual([
      {
        interruptId: "approval-17",
        status: "resolved",
        payload: { approved: true },
      },
    ]);
  });

  it("maps the visual rejection action to a denied AG-UI resume request", () => {
    const request = buildAgentFrameworkRequest(
      "thread-rejection",
      [userMessage(actionMessage("Reject report publication"), "message-rejection")],
      [approvalInterrupt],
    );

    expect(request.messages).toEqual([]);
    expect(request.availableInterrupts).toEqual([approvalInterrupt]);
    expect(request.resume).toEqual([
      {
        interruptId: "approval-17",
        status: "resolved",
        payload: { approved: false },
      },
    ]);
  });

  it("does not treat typed approval-like prose as an approval action", () => {
    const request = buildAgentFrameworkRequest(
      "thread-approval",
      [userMessage("Do not Approve and publish report yet", "message-prose")],
      [approvalInterrupt],
    );

    expect(request.messages).toHaveLength(1);
    expect(request.resume).toBeUndefined();
  });

  it("extracts canonical RUN_FINISHED interrupt outcomes", () => {
    expect(
      extractInterrupts({
        type: EventType.RUN_FINISHED,
        outcome: { type: "interrupt", interrupts: [approvalInterrupt] },
      }),
    ).toEqual([approvalInterrupt]);
  });

  it("turns an approval interrupt into streamed OpenUI Lang before RUN_FINISHED", async () => {
    const body = [
      { type: EventType.RUN_STARTED, threadId: "thread-approval", runId: "run-1" },
      {
        type: EventType.RUN_FINISHED,
        threadId: "thread-approval",
        runId: "run-1",
        outcome: { type: "interrupt", interrupts: [approvalInterrupt] },
      },
    ]
      .map((event) => `data: ${JSON.stringify(event)}\n\n`)
      .join("");
    const events = [];

    for await (const event of agentFrameworkStreamAdapter().parse(new Response(body))) {
      events.push(event);
    }

    expect(events.map((event) => event.type)).toEqual([
      EventType.RUN_STARTED,
      EventType.TEXT_MESSAGE_START,
      EventType.TEXT_MESSAGE_CONTENT,
      EventType.TEXT_MESSAGE_END,
      EventType.RUN_FINISHED,
    ]);
    expect(JSON.stringify(events)).toContain("FollowUpBlock");
    expect(JSON.stringify(events)).toContain("Approve and publish report");
    expect(JSON.stringify(events)).toContain("BarChart");
    expect(JSON.stringify(events)).toContain("FY26 Quarterly Revenue Pulse");
  });
});
