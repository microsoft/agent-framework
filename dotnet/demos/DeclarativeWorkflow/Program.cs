// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Declarative;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Shared.Diagnostics;

namespace Demo.DeclarativeWorkflow;

/// <summary>
/// HOW TO: Create a workflow from a declartive (yaml based) definition.
/// </summary>
/// <remarks>
/// Provide the path to the workflow definition file as the first argument.
/// All other arguments are intepreted as a queue of inputs.
/// When no input is queued, interactive input is requested from the console.
/// </remarks>
internal static class Program
{
    private const string DefaultWorkflow = "HelloWorld.yaml";
    //private const string HttpEventFileName = "http.log";

    public static async Task Main(string[] args)
    {
        string workflowFile = GetWorkflowFile(args);

        // Load configuration and create kernel with Azure OpenAI Chat Completion service
        IConfiguration config = InitializeConfig();

        // Create custom HTTP client with intercept handler
        //await using StreamWriter eventWriter = new(HttpEventFileName, append: false);
        //HttpInterceptor interceptor = new(eventWriter);
        //using HttpClient customClient = new(new HttpInterceptHandler() { OnIntercept = interceptor.OnResponseAsync, CheckCertificateRevocationList = true }, disposeHandler: true);
        PersistentAgentsClient client = new(Throw.IfNull(config["AzureAI:Endpoint"]), new AzureCliCredential());

        // Read and parse the declarative workflow.
        Notify($"WORKFLOW: Parsing {Path.GetFullPath(workflowFile)}");

        Stopwatch timer = Stopwatch.StartNew();
        using StreamReader yamlReader = File.OpenText(workflowFile);

        // DeclarativeWorkflowContext provides the components for workflow execution.
        DeclarativeWorkflowOptions workflowContext =
            new(projectEndpoint: Throw.IfNull(config["AzureAI:Endpoint"]))
            {
                //HttpClient = customClient, // Uncomment to use custom HTTP client
                ProjectCredentials = new AzureCliCredential(),
            };

        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        Workflow<string> workflow = DeclarativeWorkflowBuilder.Build<string>(yamlReader, workflowContext);

        Notify($"\nWORKFLOW: Defined {timer.Elapsed}");

        Notify("\nWORKFLOW: Starting...");

        // Run the workflow, just like any other workflow
        string input = GetWorkflowInput(args);
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, input);
        await MonitorWorkflowRunAsync(run, client);

        Notify("\nWORKFLOW: Done!");
    }

    private static readonly Dictionary<string, string> s_nameCache = [];

    private static async Task MonitorWorkflowRunAsync(StreamingRun run, PersistentAgentsClient client)
    {
        string? messageId = null;

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorInvokeEvent executorInvoked)
            {
                Debug.WriteLine($"STEP ENTER #{executorInvoked.ExecutorId}");
            }
            else if (evt is ExecutorCompleteEvent executorComplete)
            {
                Debug.WriteLine($"STEP EXIT #{executorComplete.ExecutorId}");
            }
            else if (evt is ExecutorFailureEvent executorFailure)
            {
                Debug.WriteLine($"STEP ERROR #{executorFailure.ExecutorId}: {executorFailure.Data?.Message ?? "Unknown"}");
            }
            else if (evt is DeclarativeWorkflowInvokeEvent invokeEvent)
            {
                Debug.WriteLine($"CONVERSATION: {invokeEvent.Data}");
            }
            else if (evt is DeclarativeWorkflowStreamEvent streamEvent)
            {
                if (!string.Equals(messageId, streamEvent.Data.MessageId, StringComparison.Ordinal))
                {
                    messageId = streamEvent.Data.MessageId;

                    if (messageId is not null)
                    {
                        string? agentId = streamEvent.Data.AuthorName;
                        if (agentId is not null)
                        {
                            if (!s_nameCache.TryGetValue(agentId, out string? realName))
                            {
                                PersistentAgent agent = await client.Administration.GetAgentAsync(agentId);
                                s_nameCache[agentId] = agent.Name;
                                realName = agent.Name;
                            }
                            agentId = realName;
                        }
                        agentId ??= nameof(ChatRole.Assistant);
                        Console.ForegroundColor = ConsoleColor.Cyan;
                        Console.Write($"\n{agentId.ToUpperInvariant()}:");
                        Console.ForegroundColor = ConsoleColor.DarkGray;
                        Console.WriteLine($" [{messageId}]");
                    }
                }
                try
                {
                    Console.ResetColor();
                    Console.Write(streamEvent.Data);
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
                    Console.WriteLine();
                    if (messageEvent.Data.MessageId is null)
                    {
                        Console.ForegroundColor = ConsoleColor.Cyan;
                        Console.WriteLine("ACTIVITY:");
                        Console.ForegroundColor = ConsoleColor.Yellow;
                        Console.WriteLine(messageEvent.Data?.Text.Trim());
                    }
                    else
                    {
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
    }

    private static string GetWorkflowFile(string[] args)
    {
        string workflowFile = args.FirstOrDefault() ?? DefaultWorkflow;

        if (!File.Exists(workflowFile) && !Path.IsPathFullyQualified(workflowFile))
        {
            workflowFile = Path.Combine(@"..\..\..\..\..\..\Workflows", workflowFile);
        }

        if (!File.Exists(workflowFile))
        {
            throw new InvalidOperationException($"Unable to locate workflow: {Path.GetFullPath(workflowFile)}.");
        }

        return workflowFile;
    }

    private static string GetWorkflowInput(string[] args)
    {
        string? input = GetWorkflowInputs(args).FirstOrDefault();

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

    private static string[] GetWorkflowInputs(string[] args)
    {
        if (args.Length == 0)
        {
            return [];
        }

        string[] workflowInput = [.. args.Skip(1)];

        return workflowInput;
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
