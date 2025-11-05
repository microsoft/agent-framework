// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Agents.MathChat;

internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        IConfiguration configuration = Application.InitializeConfig();
        string foundryEndpoint = configuration.GetValue(Application.Settings.FoundryEndpoint);
        AgentsClient agentsClient = new(new Uri(foundryEndpoint), new AzureCliCredential());

        await agentsClient.CreateAgentAsync(
            agentName: "ResearchAgent",
            agentDefinition: DefineResearchAgent(configuration),
            agentDescription: "Planner agent for DeepResearch workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "PlannerAgent",
            agentDefinition: DefinePlannerAgent(configuration),
            agentDescription: "Planner agent for DeepResearch workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "ManagerAgent",
            agentDefinition: DefineManagerAgent(configuration),
            agentDescription: "Manager agent for DeepResearch workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "SummaryAgent",
            agentDefinition: DefineSummaryAgent(configuration),
            agentDescription: "Summary agent for DeepResearch workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "KnowledgeAgent",
            agentDefinition: DefineKnowledgeAgent(configuration),
            agentDescription: "Research agent for DeepResearch workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "CoderAgent",
            agentDefinition: DefineCoderAgent(configuration),
            agentDescription: "Coder agent for DeepResearch workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "WeatherAgent",
            agentDefinition: DefineWeatherAgent(configuration),
            agentDescription: "Weather agent for DeepResearch workflow");
    }

    private static PromptAgentDefinition DefineResearchAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                In order to help begin addressing the user request, please answer the following pre-survey to the best of your ability. 
                Keep in mind that you are Ken Jennings-level with trivia, and Mensa-level with puzzles, so there should be a deep well to draw from.

                Here is the pre-survey:

                    1. Please list any specific facts or figures that are GIVEN in the request itself. It is possible that there are none.
                    2. Please list any facts that may need to be looked up, and WHERE SPECIFICALLY they might be found. In some cases, authoritative sources are mentioned in the request itself.
                    3. Please list any facts that may need to be derived (e.g., via logical deduction, simulation, or computation)
                    4. Please list any facts that are recalled from memory, hunches, well-reasoned guesses, etc.

                When answering this survey, keep in mind that 'facts' will typically be specific names, dates, statistics, etc. Your answer must only use the headings:

                    1. GIVEN OR VERIFIED FACTS
                    2. FACTS TO LOOK UP
                    3. FACTS TO DERIVE
                    4. EDUCATED GUESSES

                DO NOT include any other headings or sections in your response. DO NOT list next steps or plans until asked to do so.
                """,
            Tools =
            {
                ResponseTool.CreateWebSearchTool()
            }
        };

    private static PromptAgentDefinition DefinePlannerAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Your only job is to devise an efficient plan that identifies (by name) how a team member may contribute to addressing the user request.

                Only select the following team which is listed as "- [Name]: [Description]"

                {TeamDescription}

                The plan must be a bullet point list must be in the form "- [AgentName]: [Specific action or task for that agent to perform]"
  
                Remember, there is no requirement to involve the entire team -- only select team member's whose particular expertise is required for this task.
                """
        };

    private static PromptAgentDefinition DefineManagerAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Recall we are working on the following request:

                {InputTask}

                And we have assembled the following team:

                {TeamDescription}

                To make progress on the request, please answer the following questions, including necessary reasoning:
                - Is the request fully satisfied? (True if complete, or False if the original request has yet to be SUCCESSFULLY and FULLY addressed)
                - Are we in a loop where we are repeating the same requests and / or getting the same responses from an agent multiple times? Loops can span multiple turns, and can include repeated actions like scrolling up or down more than a handful of times.
                - Are we making forward progress? (True if just starting, or recent messages are adding value. False if recent messages show evidence of being stuck in a loop or if there is evidence of significant barriers to success such as the inability to read from a required file)
                - Who should speak next? (select from: {Concat(Local.AvailableAgents, name, ",")}) 
                - What instruction or question would you give this team member? (Phrase as if speaking directly to them, and include any specific information they may need)
                """,
            TextOptions =
                new ResponseTextOptions
                {
                    TextFormat =
                        ResponseTextFormat.CreateJsonSchemaFormat(
                            "TaskEvaluation",
                            BinaryData.FromString(
                                """
                                {
                                  "type": "object",
                                  "properties": {
                                    "is_request_satisfied": {
                                      "type": "object",
                                      "properties": {
                                        "reason": { "type": "string" },
                                        "answer": { "type": "boolean" }
                                      },
                                      "required": ["reason", "answer"],
                                      "additionalProperties": false
                                    },
                                    "is_in_loop": {
                                      "type": "object",
                                      "properties": {
                                        "reason": { "type": "string" },
                                        "answer": { "type": "boolean" }
                                      },
                                      "required": ["reason", "answer"],
                                      "additionalProperties": false
                                    },
                                    "is_progress_being_made": {
                                      "type": "object",
                                      "properties": {
                                        "reason": { "type": "string" },
                                        "answer": { "type": "boolean" }
                                      },
                                      "required": ["reason", "answer"],
                                      "additionalProperties": false
                                    },
                                    "next_speaker": {
                                      "type": "object",
                                      "properties": {
                                        "reason": { "type": "string" },
                                        "answer": {
                                          "type": "string"
                                        }
                                      },
                                      "required": ["reason", "answer"],
                                      "additionalProperties": false
                                    },
                                    "instruction_or_question": {
                                      "type": "object",
                                      "properties": {
                                        "reason": { "type": "string" },
                                        "answer": { "type": "string" }
                                      },
                                      "required": ["reason", "answer"],
                                      "additionalProperties": false
                                    }
                                  },
                                  "required": ["is_request_satisfied", "is_in_loop", "is_progress_being_made", "next_speaker", "instruction_or_question"],
                                  "additionalProperties": false
                                }
                                """),
                            jsonSchemaFormatDescription: null,
                            jsonSchemaIsStrict: true),
                }
        };

    private static PromptAgentDefinition DefineSummaryAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                We have completed the task.
                Based only on the conversation and without adding any new information, synthesize the result of the conversation as a complete response to the user task.
                The user will only ever see this last response and not the entire conversation, so please ensure it is complete and self-contained.
                We have completed the task.
                Based only on the conversation and without adding any new information, synthesize the result of the conversation as a complete response to the user task.
                The user will only ever see this last response and not the entire conversation, so please ensure it is complete and self-contained.
                """
        };

    private static PromptAgentDefinition DefineKnowledgeAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Tools =
            {
                ResponseTool.CreateWebSearchTool()
            }
        };

    private static PromptAgentDefinition DefineCoderAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Tools =
            {
                ResponseTool.CreateCodeInterpreterTool(
                    new(CodeInterpreterToolContainerConfiguration.CreateAutomaticContainerConfiguration()))
            }
        };

    private static PromptAgentDefinition DefineWeatherAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                You are a weather expert.
                """,
            Tools =
            {
                AgentTool.CreateOpenApiTool(
                    new OpenApiFunctionDefinition(
                        "weather-forecast",
                        BinaryData.FromString(File.ReadAllText("C:/Users/crickman/source/repos/af9/workflow-samples/wttr.json")), // %%% FIX PATH
                        new OpenApiAnonymousAuthDetails()))
            }
        };
}
