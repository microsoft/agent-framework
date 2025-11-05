// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
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
        TestAgentResponseHandler responseHandler,
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
        TestAgentResponseHandler responseHandler = new();

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

                // Capture output from all agents.
                services.AddSingleton<IAgentResponseHandler>(responseHandler);
            })
            .ConfigureLogging((_, logging) =>
            {
                logging.AddProvider(loggerProvider);
                logging.SetMinimumLevel(LogLevel.Debug);
            })
            .Build();
        host.Start();

        DurableTaskClient client = host.Services.GetRequiredService<DurableTaskClient>();
        return new TestHelper(loggerProvider, responseHandler, host, client);
    }

    private static string GetDurableTaskSchedulerConnectionString(IConfiguration configuration)
    {
        // The default value is for local development using the Durable Task Scheduler emulator.
        return configuration["DURABLE_TASK_SCHEDULER_CONNECTION_STRING"]
            ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";
    }

    internal static ChatClient GetAzureOpenAIChatClient(IConfiguration configuration)
    {
        string azureOpenAiEndpoint = configuration["AZURE_OPENAI_ENDPOINT"]
            ?? throw new InvalidOperationException("The required AZURE_OPENAI_ENDPOINT env variable is not set.");
        string azureOpenAiDeploymentName = configuration["AZURE_OPENAI_DEPLOYMENT"]
            ?? throw new InvalidOperationException("The required AZURE_OPENAI_DEPLOYMENT env variable is not set.");

        // Check if AZURE_OPENAI_KEY is provided for token-based authentication
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

    private sealed class TestAgentResponseHandler : IAgentResponseHandler
    {
        private readonly ConcurrentDictionary<string, List<AgentRunResponse>> _responses = [];

        public async ValueTask OnStreamingResponseUpdateAsync(
            IAsyncEnumerable<AgentRunResponseUpdate> messageStream,
            CancellationToken cancellationToken)
        {
            AgentRunResponse response = await messageStream.ToAgentRunResponseAsync(cancellationToken);
            await this.OnAgentResponseAsync(response, cancellationToken);
        }

        public ValueTask OnAgentResponseAsync(AgentRunResponse message, CancellationToken cancellationToken)
        {
            if (message.AgentId == null)
            {
                throw new InvalidOperationException("Received an agent response with a null AgentId.");
            }

            List<AgentRunResponse> threadResponses = this._responses.GetOrAdd(message.AgentId, _ => []);
            threadResponses.Add(message);

            return ValueTask.CompletedTask;
        }
    }
}
