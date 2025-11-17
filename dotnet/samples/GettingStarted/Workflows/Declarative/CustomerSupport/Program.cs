// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.CustomerSupport;

/// <summary>
/// This workflow demonstrates using multiple agents to provide automated
/// troubleshooting steps to resolve common issues with escalation options.
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

        // Create the ticketing plugin (mock functionality)
        TicketingPlugin plugin = new();

        // Ensure sample agents exist in Foundry.
        await CreateAgentsAsync(foundryEndpoint, configuration, plugin);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the workflow factory.  This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory =
            new("CustomerSupport.yaml", foundryEndpoint)
            {
                Functions =
                [
                    AIFunctionFactory.Create(plugin.CreateTicket),
                    AIFunctionFactory.Create(plugin.GetTicket),
                    AIFunctionFactory.Create(plugin.ResolveTicket),
                    AIFunctionFactory.Create(plugin.SendNotification),
                ]
            };

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentsAsync(Uri foundryEndpoint, IConfiguration configuration, TicketingPlugin plugin)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "SelfServiceAgent",
            agentDefinition: DefineSelfServiceAgent(configuration),
            agentDescription: "Service agent for CustomerSupport workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "TicketingAgent",
            agentDefinition: DefineTicketingAgent(configuration, plugin),
            agentDescription: "Ticketing agent for CustomerSupport workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "TicketRoutingAgent",
            agentDefinition: DefineTicketRoutingAgent(configuration, plugin),
            agentDescription: "Routing agent for CustomerSupport workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "WindowsSupportAgent",
            agentDefinition: DefineWindowsSupportAgent(configuration, plugin),
            agentDescription: "Windows support agent for CustomerSupport workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "TicketResolutionAgent",
            agentDefinition: DefineResolutionAgent(configuration, plugin),
            agentDescription: "Resolution agent for CustomerSupport workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "TicketEscalationAgent",
            agentDefinition: TicketEscalationAgent(configuration, plugin),
            agentDescription: "Escalate agent for human support");
    }

    private static PromptAgentDefinition DefineSelfServiceAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Use your knowledge to work with the user to provide the best possible troubleshooting steps.

                - If the user confirms that the issue is resolved, then the issue is resolved. 
                - If the user reports that the issue persists, then escalate.
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

    private static PromptAgentDefinition DefineTicketingAgent(IConfiguration configuration, TicketingPlugin plugin) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Always create a ticket in Azure DevOps using the available tools.

                Include the following information in the TicketSummary.

                - Issue description: {{IssueDescription}}
                - Attempted resolution steps: {{AttemptedResolutionSteps}}

                After creating the ticket, provide the user with the ticket ID.
                """,
            Tools =
            {
                AIFunctionFactory.Create(plugin.CreateTicket).AsOpenAIResponseTool()
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

    private static PromptAgentDefinition DefineTicketRoutingAgent(IConfiguration configuration, TicketingPlugin plugin) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Determine how to route the given issue to the appropriate support team. 

                Choose from the available teams and their functions:
                - Windows Activation Support: Windows license activation issues
                - Windows Support: Windows related issues
                - Azure Support: Azure related issues
                - Network Support: Network related issues
                - Hardware Support: Hardware related issues
                - Microsoft Office Support: Microsoft Office related issues
                - General Support: General issues not related to the above categories
                """,
            Tools =
            {
                AIFunctionFactory.Create(plugin.GetTicket).AsOpenAIResponseTool(),
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
                                    "TeamName": {
                                      "type": "string",
                                      "description": "The name of the team to route the issue"
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

    private static PromptAgentDefinition DefineWindowsSupportAgent(IConfiguration configuration, TicketingPlugin plugin) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Use your knowledge to work with the user to provide the best possible troubleshooting steps
                for issues related to Windows operating system.

                - Utilize the "Attempted Resolutions Steps" as a starting point for your troubleshooting.
                - Never escalate without troubleshooting with the user.                
                - If the user confirms that the issue is resolved, then the issue is resolved. 
                - If the user reports that the issue persists, then escalate.

                Issue: {{IssueDescription}}
                Attempted Resolution Steps: {{AttemptedResolutionSteps}}
                """,
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
            Tools =
            {
                AIFunctionFactory.Create(plugin.GetTicket).AsOpenAIResponseTool(),
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
                                    "IsResolved": {
                                      "type": "boolean",
                                      "description": "True if the user issue/ask has been resolved."
                                    },
                                    "NeedsEscalation": {
                                      "type": "boolean",
                                      "description": "True resolution could not be achieved and the issue/ask requires escalation."
                                    },
                                    "ResolutionSummary": {
                                      "type": "string",
                                      "description": "The summary of the steps that led to resolution."
                                    }
                                  },
                                  "required": ["IsResolved", "NeedsEscalation", "ResolutionSummary"],
                                  "additionalProperties": false
                                }
                                """),
                            jsonSchemaFormatDescription: null,
                            jsonSchemaIsStrict: true),
                }
        };

    private static PromptAgentDefinition DefineResolutionAgent(IConfiguration configuration, TicketingPlugin plugin) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Resolve the following ticket in Azure DevOps.
                Always include the resolution details.

                - Ticket ID: #{{TicketId}}
                - Resolution Summary: {{ResolutionSummary}}
                """,
            Tools =
            {
                AIFunctionFactory.Create(plugin.ResolveTicket).AsOpenAIResponseTool(),
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
                            Description = "The steps taken to resolve the issue.",
                        }
            }
        };

    private static PromptAgentDefinition TicketEscalationAgent(IConfiguration configuration, TicketingPlugin plugin) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                You escalate the provided issue to human support team by sending an email if the issue is not resolved.

                Here are some additional details that might help:
                - TicketId : {{TicketId}}
                - IssueDescription : {{IssueDescription}}
                - AttemptedResolutionSteps : {{AttemptedResolutionSteps}}

                Before escalating, gather the user's email address for follow-up.
                If not known, ask the user for their email address so that the support team can reach them when needed.

                When sending the email, include the following details:
                - To: support@contoso.com
                - Cc: user's email address
                - Subject of the email: "Support Ticket - {TicketId} - [Compact Issue Description]"
                - Body: 
                  - Issue description
                  - Attempted resolution steps
                  - User's email address
                  - Any other relevant information from the conversation history

                Assure the user that their issue will be resolved and provide them with a ticket ID for reference.
                """,
            Tools =
            {
                AIFunctionFactory.Create(plugin.GetTicket).AsOpenAIResponseTool(),
                AIFunctionFactory.Create(plugin.SendNotification).AsOpenAIResponseTool(),
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
                ["IssueDescription"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "A concise description of the issue.",
                    },
                ["ResolutionSummary"] =
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
                                    "IsComplete": {
                                      "type": "boolean",
                                      "description": "Has the email been sent and no more user input is required."
                                    },
                                    "UserMessage": {
                                      "type": "string",
                                      "description": "A natural language message to the user."
                                    }
                                  },
                                  "required": ["IsComplete", "UserMessage"],
                                  "additionalProperties": false
                                }
                                """),
                            jsonSchemaFormatDescription: null,
                            jsonSchemaIsStrict: true),
                }
        };
}
