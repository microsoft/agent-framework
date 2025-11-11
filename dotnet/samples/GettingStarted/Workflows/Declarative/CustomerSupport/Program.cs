// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.CustomerSupport;

/// <summary>
/// %%% COMMENT
/// </summary>
/// <remarks>
/// See the README.md file in the parent folder (../README.md) for detailed
/// information the configuration required to run this sample.
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
        WorkflowFactory workflowFactory = new("CustomerSupport.yaml", foundryEndpoint);

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentsAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        AgentClient agentClient = new(foundryEndpoint, new AzureCliCredential());

        await agentClient.CreateAgentAsync(
            agentName: "ServiceAgent",
            agentDefinition: DefineServiceAgent(configuration),
            agentDescription: "Service agent for CustomerSupport workflow");

        await agentClient.CreateAgentAsync(
            agentName: "TicketingAgent",
            agentDefinition: DefineTicketingAgent(configuration),
            agentDescription: "Ticketing agent for CustomerSupport workflow");

        await agentClient.CreateAgentAsync(
            agentName: "TicketRoutingAgent",
            agentDefinition: DefineTicketRoutingAgent(configuration),
            agentDescription: "Routing agent for CustomerSupport workflow");

        await agentClient.CreateAgentAsync(
            agentName: "WindowsSupportAgent",
            agentDefinition: DefineWindowsSupportAgent(configuration),
            agentDescription: "Windows support agent for CustomerSupport workflow");

        await agentClient.CreateAgentAsync(
            agentName: "TicketResolutionAgent",
            agentDefinition: DefineResolutionAgent(configuration),
            agentDescription: "Resolution agent for CustomerSupport workflow");

        await agentClient.CreateAgentAsync(
            agentName: "TicketEscalationAgent",
            agentDefinition: TicketEscalationAgent(configuration),
            agentDescription: "Escalate agent for human support");
    }

    private static PromptAgentDefinition DefineServiceAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                // %%% INSTRUCTIONS
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
                                    "IsResolved": {
                                      "type": "boolean",
                                      "description": "True if the user issue/ask has been resolved."
                                    },
                                    "NeedsTicket": {
                                      "type": "boolean",
                                      "description": "True if the user issue/ask requires that a ticket be filed."
                                    },
                                    "IssueDescription": {
                                      "type": "string",
                                      "description": "A concise description of the issue."
                                    },
                                    "AttemptedResolutionSteps": {
                                      "type": "string",
                                      "description": "An outline of the steps taken to attempt resolution."
                                    }                              
                                  },
                                  "required": ["IsResolved", "NeedsTicket", "IssueDescription", "AttemptedResolutionSteps"],
                                  "additionalProperties": false
                                }
                                """),
                            jsonSchemaFormatDescription: null,
                            jsonSchemaIsStrict: true),
                }
        };

    private static PromptAgentDefinition DefineTicketingAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                // %%% INSTRUCTIONS
                """,
            Tools =
            {
                // %%% TOOL: Define ticket creation tool
            },
            StructuredInputs =
            {
                ["IssueDescription"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "A concise description of the issue.",
                    },
                ["AttemptedResolutionSteps"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "An outline of the steps taken to attempt resolution.",
                    }
            },
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
                                    "TicketId": {
                                      "type": "string",
                                      "description": "The identifier of the ticket created in response to the user issue."
                                    },
                                    "TicketSummary": {
                                      "type": "string",
                                      "description": "The summary of the ticket created in response to the user issue."
                                    }
                                  },
                                  "required": ["TicketId", "TicketSummary"],
                                  "additionalProperties": false
                                }
                                """),
                            jsonSchemaFormatDescription: null,
                            jsonSchemaIsStrict: true),
                }
        };

    private static PromptAgentDefinition DefineTicketRoutingAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                // %%% INSTRUCTIONS
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
                                    "TeamName": {
                                      "type": "string",
                                      "description": "The name of the team to route the issue: 'Windows Support' or 'Escalate'"
                                    }
                                  },
                                  "required": ["TeamName"],
                                  "additionalProperties": false
                                }
                                """),
                            jsonSchemaFormatDescription: null,
                            jsonSchemaIsStrict: true),
                }
        };

    private static PromptAgentDefinition DefineWindowsSupportAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                // %%% INSTRUCTIONS
                """,
            Tools =
            {
                // %%% TOOL: Define ticket creation tool
            },
            StructuredInputs =
            {
                ["IssueDescription"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "A concise description of the issue.",
                    },
                ["AttemptedResolutionSteps"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "An outline of the steps taken to attempt resolution.",
                    }
            },
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
                                    "TicketId": {
                                      "type": "string",
                                      "description": "The identifier of the ticket created in response to the user issue."
                                    },
                                    "TicketSummary": {
                                      "type": "string",
                                      "description": "The summary of the ticket created in response to the user issue."
                                    }
                                  },
                                  "required": ["TicketId", "TicketSummary"],
                                  "additionalProperties": false
                                }
                                """),
                            jsonSchemaFormatDescription: null,
                            jsonSchemaIsStrict: true),
                }
        };

    private static PromptAgentDefinition DefineResolutionAgent(IConfiguration configuration) =>
    new(configuration.GetValue(Application.Settings.FoundryModelMini))
    {
        Instructions =
            """
                // %%% INSTRUCTIONS
                """,
        Tools =
        {
            // %%% TOOL: Define ticket creation tool
        },
        StructuredInputs =
        {
                ["TicketId"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "The identifier of the ticket being resolved.",
                    },
                ["ResolutionSummary"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "// %%% DESCRIPTION",
                    }
        }
    };

    private static PromptAgentDefinition TicketEscalationAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                // %%% INSTRUCTIONS
                """,
            Tools =
            {
                // %%% TOOL: Define ticket assignment tool
            },
            StructuredInputs =
            {
                ["TicketId"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "The identifier of the ticket being escalated.",
                    },
                ["ResolutionSummary"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "// %%% DESCRIPTION",
                    }
            }
        };
}
