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

        IHost host = Host.CreateDefaultBuilder()
            .ConfigureServices((ctx, services) =>
            {
                string dtsConnectionString = GetDurableTaskSchedulerConnectionString(ctx.Configuration);

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

    private static string GetDurableTaskSchedulerConnectionString(IConfiguration configuration)
    {
        // The default value is for local development using the Durable Task Scheduler emulator.
        return configuration["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"]
            ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";
    }

    internal static ChatClient GetAzureOpenAIChatClient(IConfiguration configuration)
    {
        string azureOpenAiEndpoint = configuration["AZURE_OPENAI_ENDPOINT"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_ENDPOINT env variable is not set.");
        string azureOpenAiDeploymentName = configuration["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"] ??
            throw new InvalidOperationException("The required AZURE_OPENAI_CHAT_DEPLOYMENT_NAME env variable is not set.");

        // Check if AZURE_OPENAI_KEY is provided for key-based authentication.
        // NOTE: This is not used for automated tests, but can be useful for local development.
        string? azureOpenAiKey = configuration["AZURE_OPENAI_KEY"];

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
