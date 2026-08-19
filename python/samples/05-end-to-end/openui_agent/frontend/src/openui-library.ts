// Copyright (c) Microsoft. All rights reserved.

import {
  openuiChatAdditionalRules,
  openuiChatExamples,
  openuiChatLibrary,
} from "@openuidev/react-ui";
import type { PromptOptions } from "@openuidev/react-lang";

export const agentFrameworkExample = `root = Card([header, chart, summary, followUps])
header = CardHeader("Quarterly revenue", "Revenue by quarter in thousands of dollars")
chart = BarChart(labels, [revenue])
labels = ["Q1", "Q2", "Q3", "Q4"]
revenue = Series("Revenue", [120, 180, 150, 240])
summary = Callout("success", "Strongest quarter", "Q4 led at $240K; Q1 was lowest at $120K.")
followUps = FollowUpBlock([compare, forecast])
compare = FollowUpItem("Compare the strongest and weakest quarter")
forecast = FollowUpItem("Forecast the next quarter")`;

export const estimateFormExample = `root = Card([header, form, followUps])
header = CardHeader("Project estimate", "Tell me what the team is planning")
form = Form("project-estimate", buttons, [projectField, teamField, notesField])
projectField = FormControl("Project name", Input("projectName", "Aurora-731", "text", { required: true }))
teamField = FormControl("Team size", Input("teamSize", "7", "number", { required: true, min: 1 }))
notesField = FormControl("Notes", TextArea("notes", "Prioritize accessibility and charts", 4, { required: true, minLength: 5 }))
buttons = Buttons([Button("Submit estimate", Action([@ToAssistant("Submit the project estimate")]), "primary")])
followUps = FollowUpBlock([help])
help = FollowUpItem("What information improves an estimate?")`;

export const promptOptions: PromptOptions = {
  preamble:
    "You are the generative UI layer for a Microsoft Agent Framework assistant. Return only valid OpenUI Lang. " +
    "Never wrap it in Markdown or expose the source syntax as prose.",
  examples: [
    ...openuiChatExamples,
    `Example — quarterly revenue chart with follow-ups:\n\n${agentFrameworkExample}`,
    `Example — validated project estimate form:\n\n${estimateFormExample}`,
  ],
  additionalRules: [
    ...openuiChatAdditionalRules,
    "Put the root = Card(...) statement first so the interface can render while the response streams.",
    "Use a visible chart component whenever the user requests a chart, graph, trend, or quarterly comparison.",
    "Preserve every numeric value supplied by the user or returned by an Agent Framework tool.",
    "End every normal response with a FollowUpBlock containing exactly two relevant FollowUpItem suggestions.",
    "When the user asks for a form, use FormControl fields with validation and a primary Button whose Action contains @ToAssistant.",
    "When action context contains submitted form values, acknowledge the distinctive values in the next rendered response.",
    "After an approval-gated tool is approved, show a success Callout and preserve any quarterly values in a visible chart.",
    "After an approval-gated tool is rejected, show an error or neutral Callout and clearly state that no action was performed.",
  ],
};

export const library = openuiChatLibrary;
