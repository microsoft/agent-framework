// Copyright (c) Microsoft. All rights reserved.

// Uncomment this to enable JSON checkpointing to the local file system.
//#define CHECKPOINT_JSON

using System.Diagnostics;
using System.Reflection;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Declarative;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.Workflows;

namespace Demo.DeclarativeWorkflow;

/// <summary>
/// HOW TO: Create a workflow from a declarative (yaml based) definition.
/// </summary>
/// <remarks>
/// <b>Configuration</b>
/// Define FOUNDRY_PROJECT_ENDPOINT as a user-secret or environment variable that
/// points to your Foundry project endpoint.
/// <b>Usage</b>
/// Provide the path to the workflow definition file as the first argument.
/// All other arguments are intepreted as a queue of inputs.
/// When no input is queued, interactive input is requested from the console.
/// </remarks>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        string? workflowFile = ParseWorkflowFile(args);
        if (workflowFile is null)
        {
            Notify("\nUsage: DeclarativeWorkflow <workflow-file> [<input>]\n");
            return;
        }

        string? workflowInput = ParseWorkflowInput(args);

        Program program = new(workflowFile, workflowInput);
        await program.ExecuteAsync();
    }

    private async Task ExecuteAsync()
    {
        // Read and parse the declarative workflow.
        Notify($"\nWORKFLOW: Parsing {Path.GetFullPath(this.WorkflowFile)}");

        Stopwatch timer = Stopwatch.StartNew();

        Workflow workflow = this.CreateWorkflow();

        Notify($"\nWORKFLOW: Defined {timer.Elapsed}");

        Notify("\nWORKFLOW: Starting...");

        string input = this.GetWorkflowInput();

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        await this.Runner.ExecuteAsync(this.CreateWorkflow, input);
    }

    /// <summary>
    /// Create the workflow from the declarative YAML.  Includes definition of the
    /// <see cref="DeclarativeWorkflowOptions" /> and the associated <see cref="WorkflowAgentProvider"/>.
    /// </summary>
    private Workflow CreateWorkflow()
    {
        // Create the agent provider that will service agent requests within the workflow.
        AzureAgentProvider agentProvider = new(new Uri(this.FoundryEndpoint), new AzureCliCredential())
        {
            // Functions included here will be auto-executed by the framework.
            Functions = this.Functions
        };

        // Define the workflow options.
        DeclarativeWorkflowOptions options =
            new(agentProvider)
            {
                Configuration = this.Configuration,
                //ConversationId = null, // Assign to continue a conversation
                //LoggerFactory = null, // Assign to enable logging
            };

        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        return DeclarativeWorkflowBuilder.Build<string>(this.WorkflowFile, options);
    }

    private string WorkflowFile { get; }
    private string? WorkflowInput { get; }
    private string FoundryEndpoint { get; }
    private IConfiguration Configuration { get; }
    private WorkflowRunner Runner { get; }
    private IList<AIFunction> Functions { get; }

    private Program(string workflowFile, string? workflowInput)
    {
        this.WorkflowFile = workflowFile;
        this.WorkflowInput = workflowInput;

        this.Configuration = InitializeConfig();

        this.FoundryEndpoint = this.Configuration[Application.Settings.FoundryEndpoint] ?? throw new InvalidOperationException($"Undefined configuration setting: {Application.Settings.FoundryEndpoint}");

        this.Functions =
            [
                // Manually define any custom functions that may be required by agents within the workflow.
                // By default, this sample does not include any functions.
                //AIFunctionFactory.Create(),
            ];

        this.Runner =
            new(this.Functions)
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

    private static string? ParseWorkflowFile(string[] args)
    {
        string? workflowFile = args.FirstOrDefault();
        if (string.IsNullOrWhiteSpace(workflowFile))
        {
            return null;
        }

        if (!File.Exists(workflowFile) && !Path.IsPathFullyQualified(workflowFile))
        {
            string? repoFolder = GetRepoFolder();
            if (repoFolder is not null)
            {
                workflowFile = Path.Combine(repoFolder, "workflow-samples", workflowFile);
                workflowFile = Path.ChangeExtension(workflowFile, ".yaml");
            }
        }

        if (!File.Exists(workflowFile))
        {
            throw new InvalidOperationException($"Unable to locate workflow: {Path.GetFullPath(workflowFile)}.");
        }

        return workflowFile;

        static string? GetRepoFolder()
        {
            DirectoryInfo? current = new(Directory.GetCurrentDirectory());

            while (current is not null)
            {
                if (Directory.Exists(Path.Combine(current.FullName, ".git")))
                {
                    return current.FullName;
                }

                current = current.Parent;
            }

            return null;
        }
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
        if (args.Length == 0)
        {
            return null;
        }

        string[] workflowInput = [.. args.Skip(1)];

        return workflowInput.FirstOrDefault();
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
