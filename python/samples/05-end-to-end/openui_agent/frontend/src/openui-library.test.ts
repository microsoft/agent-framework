// Copyright (c) Microsoft. All rights reserved.

import { describe, expect, it } from "vitest";
import { createParser } from "@openuidev/react-lang";

import { approvalCard } from "./agent-framework";
import { agentFrameworkExample, estimateFormExample, library } from "./openui-library";

const parser = createParser(library.toJSONSchema(), "Card");

function expectValidOpenUI(response: string): void {
  const result = parser.parse(response);
  expect(result.meta.errors).toEqual([]);
}

describe("OpenUI library contract", () => {
  it("parses the chart and follow-up response", () => {
    expectValidOpenUI(agentFrameworkExample);
  });

  it("parses the validated form and submit action", () => {
    expectValidOpenUI(estimateFormExample);
  });

  it("parses the adapter-generated Agent Framework approval card", () => {
    expectValidOpenUI(
      approvalCard({
        id: "approval-17",
        message: "Approve running publish_revenue_report?",
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
      }),
    );
  });
});
