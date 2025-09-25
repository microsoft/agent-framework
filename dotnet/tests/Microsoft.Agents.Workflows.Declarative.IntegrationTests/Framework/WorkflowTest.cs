// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;

/// <summary>
/// Base class for workflow tests.
/// </summary>
public abstract class WorkflowTest(ITestOutputHelper output) : IntegrationTest(output)
{
    protected abstract Task RunAndVerifyAsync<TInput>(Testcase testcase, string workflowPath, DeclarativeWorkflowOptions workflowOptions) where TInput : notnull;

    protected Task RunWorkflowAsync(string workflowFileName, string testcaseFileName)
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
                nameof(ChatMessage) => this.TestWorkflowAsync<ChatMessage>(testcase, workflowPath, configuration),
                nameof(String) => this.TestWorkflowAsync<string>(testcase, workflowPath, configuration),
                _ => throw new NotSupportedException($"Input type '{testcase.Setup.Input.Type}' is not supported."),
            };
    }

    protected async Task TestWorkflowAsync<TInput>(
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
        await this.RunAndVerifyAsync<TInput>(testcase, workflowPath, workflowOptions);
    }

    protected static object GetInput<TInput>(Testcase testcase) where TInput : notnull =>
        testcase.Setup.Input.Type switch
        {
            nameof(ChatMessage) => new ChatMessage(ChatRole.User, testcase.Setup.Input.Value),
            nameof(String) => testcase.Setup.Input.Value,
            _ => throw new NotSupportedException($"Input type '{testcase.Setup.Input.Type}' is not supported."),
        };

    protected static Testcase ReadTestcase(string testcaseFileName)
    {
        using Stream testcaseStream = File.Open(Path.Combine("Testcases", testcaseFileName), FileMode.Open);
        Testcase? testcase = JsonSerializer.Deserialize<Testcase>(testcaseStream, s_jsonSerializerOptions);
        Assert.NotNull(testcase);
        return testcase;
    }

    protected static readonly JsonSerializerOptions s_jsonSerializerOptions = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
    };
}
