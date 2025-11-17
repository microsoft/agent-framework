// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Reflection;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;

/// <summary>
/// Base class for workflow tests.
/// </summary>
public abstract class IntegrationTest : IDisposable
{
    private IConfigurationRoot? _configuration;

    protected IConfigurationRoot Configuration => this._configuration ??= InitializeConfig();

    public Uri TestEndpoint { get; }

    public TestOutputAdapter Output { get; }

    protected IntegrationTest(ITestOutputHelper output)
    {
        this.Output = new TestOutputAdapter(output);
        this.TestEndpoint =
            new Uri(
                this.Configuration[AgentProvider.Settings.FoundryEndpoint] ??
                throw new InvalidOperationException($"Undefined configuration setting: {AgentProvider.Settings.FoundryEndpoint}"));
        Console.SetOut(this.Output);
        SetProduct();
    }

    public void Dispose()
    {
        this.Dispose(isDisposing: true);
        GC.SuppressFinalize(this);
    }

    protected virtual void Dispose(bool isDisposing)
    {
        if (isDisposing)
        {
            this.Output.Dispose();
        }
    }

    protected static void SetProduct()
    {
        if (!ProductContext.IsLocalScopeSupported())
        {
            ProductContext.SetContext(Product.Foundry);
        }
    }

    internal static string FormatVariablePath(string variableName, string? scope = null) => $"{scope ?? WorkflowFormulaState.DefaultScopeName}.{variableName}";

    protected async ValueTask<DeclarativeWorkflowOptions> CreateOptionsAsync(bool externalConversation = false, params IEnumerable<AIFunction> functionTools)
    {
        AzureAgentProvider agentProvider =
            new(this.TestEndpoint, new AzureCliCredential())
            {
                Functions = functionTools,
            };

        string? conversationId = null;
        if (externalConversation)
        {
            conversationId = await agentProvider.CreateConversationAsync().ConfigureAwait(false);
        }

        return
            new DeclarativeWorkflowOptions(agentProvider)
            {
                ConversationId = conversationId,
                LoggerFactory = this.Output
            };
    }

    private static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddEnvironmentVariables()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .Build();
}
