// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Declarative;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Demo.DeclarativeWorkflow;

internal static class Program
{
    public static async Task Main(string[] args)
    {
        // Load configuration and create kernel with Azure OpenAI Chat Completion service
        IConfiguration config = InitializeConfig();

        Notify("PROCESS INIT\n");

        Stopwatch timer = Stopwatch.StartNew();

        //////////////////////////////////////////////////////
        //
        // HOW TO: Create a workflow from a YAML file.
        //
        using StreamReader yamlReader = File.OpenText("demo250729.yaml");
        //
        // DeclarativeWorkflowContext provides the components for workflow execution.
        //
        DeclarativeWorkflowContext workflowContext =
            new()
            {
                LoggerFactory = NullLoggerFactory.Instance,
                ActivityChannel = System.Console.Out,
                ProjectEndpoint = Throw.IfNull(config["AzureAI:Endpoint"]),
                ProjectCredentials = new AzureCliCredential(),
            };
        //
        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        //
        Workflow<string> workflow = DeclarativeWorkflowBuilder.Build(yamlReader, workflowContext);
        //
        //////////////////////////////////////////////////////

        Notify($"PROCESS DEFINED: {timer.Elapsed}\n");

        Notify("PROCESS INVOKE\n");

        //////////////////////////////////////////////
        // Run the workflow, just like any other workflow
        LocalRunner<string> runner = new(workflow);
        StreamingRun handle = await runner.StreamAsync("<placeholder>");
        await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorInvokeEvent executorInvoked)
            {
                Debug.WriteLine($"!!! ENTER #{executorInvoked.ExecutorId}");
            }
            else if (evt is ExecutorCompleteEvent executorComplete)
            {
                Debug.WriteLine($"!!! EXIT #{executorComplete.ExecutorId}");
            }
        }
        //////////////////////////////////////////////

        Notify("PROCESS DONE");
    }

    // Load configuration from user-secrets
    private static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
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
