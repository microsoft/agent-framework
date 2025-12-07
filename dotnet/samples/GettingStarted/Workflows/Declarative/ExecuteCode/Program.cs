// Copyright (c) Microsoft. All rights reserved.

// Uncomment this to enable JSON checkpointing to the local file system.
//#define CHECKPOINT_JSON

using System.Reflection;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Declarative;
using Microsoft.Extensions.Configuration;
using Shared.Workflows;

namespace Demo.DeclarativeCode;

/// <summary>
/// HOW TO: Execute a declarative workflow that has been converted to code.
/// </summary>
/// <remarks>
/// <b>Configuration</b>
/// Define FOUNDRY_PROJECT_ENDPOINT as a user-secret or environment variable that
/// points to your Foundry project endpoint.
/// </remarks>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        string? workflowInput = ParseWorkflowInput(args);

        Program program = new(workflowInput);
        await program.ExecuteAsync();
    }

    private async Task ExecuteAsync()
    {
        Notify("\nWORKFLOW: Starting...");

        string input = this.GetWorkflowInput();

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        await this.Runner.ExecuteAsync(this.CreateWorkflow, input);

        Notify("\nWORKFLOW: Done!\n");
    }

    private Workflow CreateWorkflow()
    {
        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        DeclarativeWorkflowOptions options =
            new(new AzureAgentProvider(new Uri(this.FoundryEndpoint), new AzureCliCredential()))
            {
                Configuration = this.Configuration
            };

        // Use the generated provider to create a workflow instance.
        return SampleWorkflowProvider.CreateWorkflow<string>(options);
    }

    private string? WorkflowInput { get; }
    private string FoundryEndpoint { get; }
    private IConfiguration Configuration { get; }
    private WorkflowRunner Runner { get; }

    private Program(string? workflowInput)
    {
        this.WorkflowInput = workflowInput;

        this.Configuration = InitializeConfig();

        this.FoundryEndpoint = this.Configuration[Application.Settings.FoundryEndpoint] ?? throw new InvalidOperationException($"Undefined configuration setting: {Application.Settings.FoundryEndpoint}");

        this.Runner =
            new()
            {
#if CHECKPOINT_JSON
                // Use an json file checkpoint store that will persist checkpoints to the local file system.
                UseJsonCheckpoints = true
#else
                // Use an in-memory checkpoint store that will not persist checkpoints beyond the lifetime of the process.
                UseJsonCheckpoints = false
#endif
            };
    }

    private string GetWorkflowInput()
    {
        string? input = this.WorkflowInput;

        try
        {
            Console.ForegroundColor = ConsoleColor.DarkGreen;

            Console.Write("\nINPUT: ");

            Console.ForegroundColor = ConsoleColor.White;

            if (!string.IsNullOrWhiteSpace(input))
            {
                Console.WriteLine(input);
                return input;
            }
            while (string.IsNullOrWhiteSpace(input))
            {
                input = Console.ReadLine();
            }

            return input.Trim();
        }
        finally
        {
            Console.ResetColor();
        }
    }

    private static string? ParseWorkflowInput(string[] args)
    {
        return args?.FirstOrDefault();
    }

    // Load configuration from user-secrets
    private static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

    private static void Notify(string message)
    {
        Console.ForegroundColor = ConsoleColor.Cyan;
        try
        {
            Console.WriteLine(message);
        }
        finally
        {
            Console.ResetColor();
        }
    }
}
