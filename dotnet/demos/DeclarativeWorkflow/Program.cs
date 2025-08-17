// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Declarative;
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
        using StreamReader yamlReader = File.OpenText(args.FirstOrDefault() ?? "demo250729.yaml");
        //
        // DeclarativeWorkflowContext provides the components for workflow execution.
        //
        DeclarativeWorkflowContext workflowContext =
            new()
            {
                LoggerFactory = NullLoggerFactory.Instance,
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
        string? messageId = null;
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, "What is the formula for fibbinocci sequence");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorInvokeEvent executorInvoked)
            {
                Debug.WriteLine($"!!! ENTER #{executorInvoked.ExecutorId}");
            }
            else if (evt is ExecutorCompleteEvent executorComplete)
            {
                Debug.WriteLine($"!!! EXIT #{executorComplete.ExecutorId}");
            }
            else if (evt is DeclarativeWorkflowStreamEvent streamEvent)
            {
                if (!string.Equals(messageId, streamEvent.Data.MessageId, StringComparison.Ordinal))
                {
                    messageId = streamEvent.Data.MessageId;

                    Console.WriteLine();

                    if (messageId is not null)
                    {
                        Console.ForegroundColor = ConsoleColor.White;
                        Console.WriteLine($"#{messageId}:");
                    }
                }
                try
                {
                    Console.ForegroundColor = ConsoleColor.Gray;
                    Console.Write(streamEvent.Data);
                    //if (streamEvent.Usage is not null)
                    //{
                    //    Console.ForegroundColor = ConsoleColor.DarkGray;
                    //    Console.WriteLine($"[Tokens Total: {streamEvent.Usage.TotalTokenCount}, Input: {streamEvent.Usage.InputTokenCount}, Output: {streamEvent.Usage.OutputTokenCount}]");
                    //}
                }
                finally
                {
                    Console.ResetColor();
                }
            }
            else if (evt is DeclarativeWorkflowMessageEvent messageEvent)
            {
                try
                {
                    Console.WriteLine(Environment.NewLine);

                    if (messageEvent.Data.MessageId is null)
                    {
                        Console.ForegroundColor = ConsoleColor.Yellow;
                        Console.WriteLine(messageEvent.Data);
                    }
                    else
                    {
                        Console.ForegroundColor = ConsoleColor.White;
                        Console.WriteLine($"#{messageEvent.Data.MessageId}:");
                        Console.ForegroundColor = ConsoleColor.DarkGreen;
                        Console.WriteLine(messageEvent.Data);
                        if (messageEvent.Usage is not null)
                        {
                            Console.ForegroundColor = ConsoleColor.DarkGray;
                            Console.WriteLine($"[Tokens Total: {messageEvent.Usage.TotalTokenCount}, Input: {messageEvent.Usage.InputTokenCount}, Output: {messageEvent.Usage.OutputTokenCount}]");
                        }
                    }
                }
                finally
                {
                    Console.ResetColor();
                }
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
