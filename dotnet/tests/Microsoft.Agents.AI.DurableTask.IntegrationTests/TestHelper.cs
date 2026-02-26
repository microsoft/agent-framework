// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI.DurableTask.IntegrationTests.Logging;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenAI.Chat;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests;

internal sealed class TestHelper : IDisposable
{
    private readonly TestLoggerProvider _loggerProvider;
    private readonly IHost _host;
    private readonly DurableTaskClient _client;

    // The static Start method should be used to create instances of this class.
    private TestHelper(
        TestLoggerProvider loggerProvider,
        IHost host,
        DurableTaskClient client)
    {
        this._loggerProvider = loggerProvider;
        this._host = host;
        this._client = client;
    }

    public IServiceProvider Services => this._host.Services;

    public void Dispose()
    {
        this._host.Dispose();
    }

    public bool TryGetLogs(string category, out IReadOnlyCollection<LogEntry> logs)
        => this._loggerProvider.TryGetLogs(category, out logs);

    public static TestHelper Start(
        AIAgent[] agents,
        ITestOutputHelper outputHelper,
        Action<DurableTaskRegistry>? durableTaskRegistry = null)
    {
        return BuildAndStartTestHelper(
            outputHelper,
            options => options.AddAIAgents(agents),
            durableTaskRegistry);
    }

    public static TestHelper Start(
        ITestOutputHelper outputHelper,
        Action<DurableAgentsOptions> configureAgents,
        Action<DurableTaskRegistry>? durableTaskRegistry = null)
    {
        return BuildAndStartTestHelper(
            outputHelper,
            configureAgents,
            durableTaskRegistry);
    }

    public DurableTaskClient GetClient() => this._client;

    private static TestHelper BuildAndStartTestHelper(
        ITestOutputHelper outputHelper,
        Action<DurableAgentsOptions> configureAgents,
        Action<DurableTaskRegistry>? durableTaskRegistry)
    {
        TestLoggerProvider loggerProvider = new(outputHelper);

        // Generate a unique TaskHub name for this test instance to prevent cross-test interference
        // when multiple tests run together and share the same DTS emulator.
        string uniqueTaskHubName = $"test-{Guid.NewGuid().ToString("N").Substring(0, 6)}";

        IHost host = Host.CreateDefaultBuilder()
            .ConfigureServices((ctx, services) =>
            {
                string dtsConnectionString = GetDurableTaskSchedulerConnectionString(ctx.Configuration, uniqueTaskHubName);

                // Register durable agents using the caller-supplied registration action and
                // apply the default chat client for agents that don't supply one themselves.
                services.ConfigureDurableAgents(
                    options => configureAgents(options),
                    workerBuilder: builder =>
                    {
                        builder.UseDurableTaskScheduler(dtsConnectionString);
                        if (durableTaskRegistry != null)
                        {
                            builder.AddTasks(durableTaskRegistry);
                        }
                    },
                    clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
            })
            .ConfigureLogging((_, logging) =>
            {
                logging.AddProvider(loggerProvider);
                logging.SetMinimumLevel(LogLevel.Debug);
            })
            .Build();
        host.Start();

        DurableTaskClient client = host.Services.GetRequiredService<DurableTaskClient>();
        return new TestHelper(loggerProvider, host, client);
    }

    private static string GetDurableTaskSchedulerConnectionString(IConfiguration configuration, string? taskHubName = null)
    {
        // The default value is for local development using the Durable Task Scheduler emulator.
        string? connectionString = configuration["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"];

        if (connectionString != null)
        {
            // If a connection string is provided, replace the TaskHub name if a custom one is specified
            if (taskHubName != null)
            {
                // Replace TaskHub in the connection string
                if (connectionString.Contains("TaskHub=", StringComparison.OrdinalIgnoreCase))
                {
                    // Find and replace the TaskHub value
                    int taskHubIndex = connectionString.IndexOf("TaskHub=", StringComparison.OrdinalIgnoreCase);
                    int taskHubValueStart = taskHubIndex + "TaskHub=".Length;
                    int taskHubValueEnd = connectionString.IndexOf(';', taskHubValueStart);
                    if (taskHubValueEnd == -1)
                    {
                        taskHubValueEnd = connectionString.Length;
                    }

                    connectionString = string.Concat(
                        connectionString.AsSpan(0, taskHubValueStart),
                        taskHubName,
                        connectionString.AsSpan(taskHubValueEnd));
                }
                else
                {
                    // Append TaskHub if it doesn't exist
                    connectionString += $";TaskHub={taskHubName}";
                }
            }

            return connectionString;
        }

        // Default connection string with unique TaskHub name
        string defaultTaskHub = taskHubName ?? "default";
        return $"Endpoint=http://localhost:8080;TaskHub={defaultTaskHub};Authentication=None";
    }

    internal static ChatClient GetAzureOpenAIChatClient(IConfiguration configuration)
    {
        string azureOpenAiEndpoint = configuration["AZURE_OPENAI_ENDPOINT"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_ENDPOINT env variable is not set.");
        string azureOpenAiDeploymentName = configuration["AZURE_OPENAI_DEPLOYMENT_NAME"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_DEPLOYMENT_NAME env variable is not set.");

        // Check if AZURE_OPENAI_API_KEY is provided for key-based authentication.
        // NOTE: This is not used for automated tests, but can be useful for local development.
        string? azureOpenAiKey = configuration["AZURE_OPENAI_API_KEY"];

        AzureOpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
            ? new AzureOpenAIClient(new Uri(azureOpenAiEndpoint), new AzureKeyCredential(azureOpenAiKey))
            : new AzureOpenAIClient(new Uri(azureOpenAiEndpoint), new AzureCliCredential());

        return client.GetChatClient(azureOpenAiDeploymentName);
    }

    internal IReadOnlyCollection<LogEntry> GetLogs()
    {
        return this._loggerProvider.GetAllLogs();
    }
}
