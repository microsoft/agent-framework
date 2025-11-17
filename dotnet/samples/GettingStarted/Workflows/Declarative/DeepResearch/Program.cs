// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.DeepResearch;

/// <summary>
/// Demonstrate a declarative workflow that accomplishes a task
/// using the Magentic orchestration pattern developed by AutoGen.
/// </summary>
/// <remarks>
/// See the README.md file in the parent folder (../README.md) for detailed
/// information about the configuration required to run this sample.
/// </remarks>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Ensure sample agents exist in Foundry.
        await CreateAgentsAsync(foundryEndpoint, configuration);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the workflow factory.  This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("DeepResearch.yaml", foundryEndpoint);

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentsAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "ResearchAgent",
            agentDefinition: DefineResearchAgent(configuration),
            agentDescription: "Planner agent for DeepResearch workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "PlannerAgent",
            agentDefinition: DefinePlannerAgent(configuration),
            agentDescription: "Planner agent for DeepResearch workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "ManagerAgent",
            agentDefinition: DefineManagerAgent(configuration),
            agentDescription: "Manager agent for DeepResearch workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "SummaryAgent",
            agentDefinition: DefineSummaryAgent(configuration),
            agentDescription: "Summary agent for DeepResearch workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "KnowledgeAgent",
            agentDefinition: DefineKnowledgeAgent(configuration),
            agentDescription: "Research agent for DeepResearch workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "CoderAgent",
            agentDefinition: DefineCoderAgent(configuration),
            agentDescription: "Coder agent for DeepResearch workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "WeatherAgent",
            agentDefinition: DefineWeatherAgent(configuration),
            agentDescription: "Weather agent for DeepResearch workflow");
    }

    private static PromptAgentDefinition DefineResearchAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelFull))
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
                //AgentTool.CreateBingGroundingTool( // TODO: Use Bing Grounding when available
                //    new BingGroundingSearchToolParameters(
                //        [new BingGroundingSearchConfiguration(this.GetSetting(Settings.FoundryGroundingTool))]))
            }
        };

    private static PromptAgentDefinition DefinePlannerAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions = // TODO: Use Structured Inputs / Prompt Template
                """
                Your only job is to devise an efficient plan that identifies (by name) how a team member may contribute to addressing the user request.

                Only select the following team which is listed as "- [Name]: [Description]"

                - WeatherAgent: Able to retrieve weather information
                - CoderAgent: Able to write and execute Python code
                - KnowledgeAgent: Able to perform generic websearches

                The plan must be a bullet point list must be in the form "- [AgentName]: [Specific action or task for that agent to perform]"
  
                Remember, there is no requirement to involve the entire team -- only select team member's whose particular expertise is required for this task.
                """
        };

    private static PromptAgentDefinition DefineManagerAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions = // TODO: Use Structured Inputs / Prompt Template
                """
                Recall we have assembled the following team:

                - KnowledgeAgent: Able to perform generic websearches
                - CoderAgent: Able to write and execute Python code
                - WeatherAgent: Able to retrieve weather information
                                
                To make progress on the request, please answer the following questions, including necessary reasoning:
                - Is the request fully satisfied? (True if complete, or False if the original request has yet to be SUCCESSFULLY and FULLY addressed)
                - Are we in a loop where we are repeating the same requests and / or getting the same responses from an agent multiple times? Loops can span multiple turns, and can include repeated actions like scrolling up or down more than a handful of times.
                - Are we making forward progress? (True if just starting, or recent messages are adding value. False if recent messages show evidence of being stuck in a loop or if there is evidence of significant barriers to success such as the inability to read from a required file)
                - Who should speak next? (select from: KnowledgeAgent, CoderAgent, WeatherAgent) 
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

                Based only on the conversation and without adding any new information,
                synthesize the result of the conversation as a complete response to the user task.

                The user will only ever see this last response and not the entire conversation,
                so please ensure it is complete and self-contained.
                """
        };

    private static PromptAgentDefinition DefineKnowledgeAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Tools =
            {
                //AgentTool.CreateBingGroundingTool( // TODO: Use Bing Grounding when available
                //    new BingGroundingSearchToolParameters(
                //        [new BingGroundingSearchConfiguration(this.GetSetting(Settings.FoundryGroundingTool))]))
            }
        };

    private static PromptAgentDefinition DefineCoderAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                You solve problem by writing and executing code.
                """,
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
                    new OpenAPIFunctionDefinition(
                        "weather-forecast",
                        BinaryData.FromString(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "wttr.json"))),
                        new OpenAPIAnonymousAuthenticationDetails()))
            }
        };
}
