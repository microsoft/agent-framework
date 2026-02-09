// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.InputArguments;

/// <summary>
/// Demonstrate a workflow that consumes input arguments to dynamically enhance the agent
/// instructions.  Exits the loop when the user enters "exit".
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
        await CreateAgentAsync(foundryEndpoint, configuration);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the workflow factory.  This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("InputArguments.yaml", foundryEndpoint);

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "LocationTriageAgent",
            agentDefinition: DefineLocationTriageAgent(configuration),
            agentDescription: "Chats with the user to solicit a location of interest.");

        await aiProjectClient.CreateAgentAsync(
            agentName: "LocationCaptureAgent",
            agentDefinition: DefineLocationCaptureAgent(configuration),
            agentDescription: "Evaluate the status of soliciting the location.");

        await aiProjectClient.CreateAgentAsync(
            agentName: "LocationAwareAgent",
            agentDefinition: DefineLocationAwareAgent(configuration),
            agentDescription: "Chats with the user with location awareness.");
    }

    private static PromptAgentDefinition DefineLocationTriageAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Your only job is to solicit a location from the user.

                Always repeat back the location when addressing the user, except when it is not known.
                """
        };

    private static PromptAgentDefinition DefineLocationCaptureAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Request a location from the user.  This location could be their own location
                or perhaps a location they are interested in.

                City level precision is sufficient.

                If extrapolating region and country, confirm you have it right.
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
                                    "place": {
                                      "type": "string",
                                      "description": "Captures only your understanding of the location specified by the user without explanation, or 'unknown' if not yet defined."
                                    },
                                    "action": {
                                      "type": "string",
                                      "description": "The instruction for the next action to take regarding the need for additional detail or confirmation."
                                    },
                                    "is_location_defined": {
                                      "type": "boolean",
                                      "description": "True if the user location is understood."
                                    },
                                    "is_location_confirmed": {
                                      "type": "boolean",
                                      "description": "True if the user location is confirmed.  An unambiguous location may be implicitly confirmed without explicit user confirmation."
                                    }
                                  },
                                  "required": ["place", "action", "is_location_defined", "is_location_confirmed"],
                                  "additionalProperties": false
                                }
                                """),
                            jsonSchemaFormatDescription: null,
                            jsonSchemaIsStrict: true),
                }
        };

    private static PromptAgentDefinition DefineLocationAwareAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            // Parameterized instructions reference the "location" input argument.
            Instructions =
                """
                Talk to the user about their request.
                Their request is related to a specific location: {{location}}.
                """,
            StructuredInputs =
            {
                ["location"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "The user's location",
                    }
            }
        };
}
