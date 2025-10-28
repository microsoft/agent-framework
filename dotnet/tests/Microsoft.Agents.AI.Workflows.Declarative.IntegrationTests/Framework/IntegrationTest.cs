// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.Reflection;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;

/// <summary>
/// Base class for workflow tests.
/// </summary>
public abstract class IntegrationTest : IDisposable
{
    private IConfigurationRoot? _configuration;
    private AzureAIConfiguration? _foundryConfiguration;

    protected IConfigurationRoot Configuration => this._configuration ??= InitializeConfig();

    internal AzureAIConfiguration FoundryConfiguration
    {
        get
        {
            this._foundryConfiguration ??= this.Configuration.GetSection("AzureAI").Get<AzureAIConfiguration>();
            Assert.NotNull(this._foundryConfiguration);
            return this._foundryConfiguration;
        }
    }

    public TestOutputAdapter Output { get; }

    protected IntegrationTest(ITestOutputHelper output)
    {
        this.Output = new TestOutputAdapter(output);
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
        FrozenDictionary<string, string?> agentMap = await AgentFactory.GetAgentsAsync(this.FoundryConfiguration, this.Configuration);

        IConfiguration workflowConfig =
            new ConfigurationBuilder()
                .AddInMemoryCollection(agentMap)
                .Build();

        AzureAgentProvider agentProvider =
            new(this.FoundryConfiguration.Endpoint, new AzureCliCredential())
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
                Configuration = workflowConfig,
                ConversationId = conversationId,
                LoggerFactory = this.Output
            };
    }

    private static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddJsonFile("appsettings.Development.json", true)
            .AddEnvironmentVariables()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .Build();
}
