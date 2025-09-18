// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
[Collection("Global")]
public sealed class DeclarativeWorkflowTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("SendActivity.yaml", "SendActivity.json")]
    [InlineData("InvokeAgent.yaml", "InvokeAgent.json")]
    public Task ValidateAsync(string workflowFileName, string testcaseFileName) =>
        this.RunWorkflowAsync(workflowFileName, testcaseFileName);

    private Task RunWorkflowAsync(string workflowFileName, string testcaseFileName)
    {
        this.Output.WriteLine($"WORKFLOW: {workflowFileName}");
        this.Output.WriteLine($"TESTCASE: {testcaseFileName}");

        Testcase testcase = ReadTestcase(testcaseFileName);
        IConfiguration configuration = InitializeConfig();
        string workflowPath = Path.Combine("Workflows", workflowFileName);

        this.Output.WriteLine($"          {testcase.Description}");

        return
            testcase.Setup.Input.Type switch
            {
                nameof(ChatMessage) => this.RunWorkflowAsync<ChatMessage>(testcase, workflowPath, configuration),
                nameof(String) => this.RunWorkflowAsync<string>(testcase, workflowPath, configuration),
                _ => throw new NotSupportedException($"Input type '{testcase.Setup.Input.Type}' is not supported."),
            };
    }

    private async Task RunWorkflowAsync<TInput>(
        Testcase testcase,
        string workflowPath,
        IConfiguration configuration) where TInput : notnull
    {
        this.Output.WriteLine($"INPUT: {testcase.Setup.Input.Value}");

        AzureAIConfiguration? foundryConfig = configuration.GetSection("AzureAI").Get<AzureAIConfiguration>();
        Assert.NotNull(foundryConfig);

        IReadOnlyDictionary<string, string?> agentMap = await AgentFixture.GetAgentsAsync(foundryConfig);

        IConfiguration workflowConfig =
            new ConfigurationBuilder()
                .AddInMemoryCollection(agentMap)
                .Build();

        DeclarativeWorkflowOptions workflowOptions =
            new(new AzureAgentProvider(foundryConfig.Endpoint, new AzureCliCredential()))
            {
                Configuration = workflowConfig,
                LoggerFactory = this.Output
            };
        Workflow<TInput> workflow = DeclarativeWorkflowBuilder.Build<TInput>(workflowPath, workflowOptions);

        WorkflowEvents workflowEvents = await WorkflowHarness.RunAsync(workflow, (TInput)GetInput<TInput>(testcase));
        foreach (DeclarativeActionInvokedEvent actionInvokeEvent in workflowEvents.ActionInvokeEvents)
        {
            this.Output.WriteLine($"ACTION: {actionInvokeEvent.ActionId} [{actionInvokeEvent.ActionType}]");
        }

        Assert.Equal(testcase.Validation.ActionCount, workflowEvents.ActionInvokeEvents.Count);
        Assert.Equal(testcase.Validation.ActionCount, workflowEvents.ActionCompleteEvents.Count);
    }

    private static object GetInput<TInput>(Testcase testcase) where TInput : notnull =>
        testcase.Setup.Input.Type switch
        {
            nameof(ChatMessage) => new ChatMessage(ChatRole.User, testcase.Setup.Input.Value),
            nameof(String) => testcase.Setup.Input.Value,
            _ => throw new NotSupportedException($"Input type '{testcase.Setup.Input.Type}' is not supported."),
        };

    private static Testcase ReadTestcase(string testcaseFileName)
    {
        using Stream testcaseStream = File.Open(Path.Combine("Testcases", testcaseFileName), FileMode.Open);
        Testcase? testcase = JsonSerializer.Deserialize<Testcase>(testcaseStream, s_jsonSerializerOptions);
        Assert.NotNull(testcase);
        return testcase;
    }

    private static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

    private static readonly JsonSerializerOptions s_jsonSerializerOptions = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
    };
}
