// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
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
    private const string DefaultWorkflow = "HelloWorld.yaml";
    private const string HttpEventFileName = "http.log";

    public static async Task Main(string[] args)
    {
        string workflowFile = GetWorkflowFile(args);

        // Load configuration and create kernel with Azure OpenAI Chat Completion service
        IConfiguration config = InitializeConfig();

        // Create custom HTTP client with intercept handler
        await using StreamWriter eventWriter = new(HttpEventFileName, append: false);
        using HttpClient customClient = new(new HttpInterceptHandler() { OnIntercept = OnHttpIntercept, CheckCertificateRevocationList = true }, disposeHandler: true);

        // Read and parse the declarative workflow.
        Notify("PROCESS INIT");

        Stopwatch timer = Stopwatch.StartNew();

        //////////////////////////////////////////////////////
        //
        // HOW TO: Create a workflow from a YAML file.
        //
        using StreamReader yamlReader = File.OpenText(workflowFile);
        //
        // DeclarativeWorkflowContext provides the components for workflow execution.
        //
        DeclarativeWorkflowOptions workflowContext =
            new()
            {
                HttpClient = customClient,
                LoggerFactory = NullLoggerFactory.Instance,
                ProjectEndpoint = Throw.IfNull(config["AzureAI:Endpoint"]),
                ProjectCredentials = new AzureCliCredential(),
            };
        //
        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        //
        Workflow<string> workflow = DeclarativeWorkflowBuilder.Build<string>(yamlReader, workflowContext);
        //
        //////////////////////////////////////////////////////

        Notify($"\nPROCESS DEFINED: {timer.Elapsed}");

        Notify("\nPROCESS INVOKE");

        //////////////////////////////////////////////
        // Run the workflow, just like any other workflow
        string? messageId = null;
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, GetWorkflowInput(args));
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
            else if (evt is ExecutorFailureEvent executorFailure)
            {
                Debug.WriteLine($"!!! ERROR #{executorFailure.ExecutorId}: {executorFailure.Data?.Message ?? "Unknown"}");
            }
            else if (evt is DeclarativeWorkflowStreamEvent streamEvent)
            {
                if (!string.Equals(messageId, streamEvent.Data.MessageId, StringComparison.Ordinal))
                {
                    messageId = streamEvent.Data.MessageId;

                    Console.WriteLine();

                    if (messageId is not null)
                    {
                        Console.ForegroundColor = ConsoleColor.Cyan;
                        Console.WriteLine($"#{messageId}:");
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
        //////////////////////////////////////////////

        Notify("\nPROCESS DONE");

        string GetWorkflowInput(string[] args)
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

                Console.WriteLine();

                return input.Trim();
            }
            finally
            {
                Console.ResetColor();
            }
        }

        ValueTask OnHttpIntercept(HttpResponseIntercept intercept)
        {
            eventWriter.WriteLine($"{intercept.RequestMethod} {intercept.RequestUri}");
            if (intercept.ResponseContent is not null)
            {
                eventWriter.WriteLine($"API:{Environment.NewLine}" + intercept.ResponseContent);
            }
            return default;
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
