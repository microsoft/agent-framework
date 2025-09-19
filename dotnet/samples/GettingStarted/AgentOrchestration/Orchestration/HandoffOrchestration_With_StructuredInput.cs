// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Orchestration;

/// <summary>
/// Demonstrates how to use the <see cref="HandoffOrchestration"/>.
/// </summary>
public class HandoffOrchestration_With_StructuredInput(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Fact]
    public async Task RunOrchestrationAsync()
    {
        // Initialize plugin
        GithubPlugin githubPlugin = new();
        AIFunction githubAddLabelFunction = AIFunctionFactory.Create(githubPlugin.AddLabels);

        // Define the agents
        ChatClientAgent triageAgent =
            CreateAgent(
                instructions: "Given a GitHub issue, triage it.",
                name: "TriageAgent",
                description: "An agent that triages GitHub issues");
        ChatClientAgent pythonAgent =
            CreateAgent(
                instructions: "You are an agent that handles Python related GitHub issues.",
                name: "PythonAgent",
                description: "An agent that handles Python related issues",
                functions: githubAddLabelFunction);
        ChatClientAgent dotnetAgent =
            CreateAgent(
                instructions: "You are an agent that handles .NET related GitHub issues.",
                name: "DotNetAgent",
                description: "An agent that handles .NET related issues",
                functions: githubAddLabelFunction);

        // Create a monitor to capturing agent responses (via ResponseCallback)
        // to display at the end of this sample. (optional)
        // NOTE: Create your own callback to capture responses in your application or service.
        OrchestrationMonitor monitor = new();

        // Define the orchestration
        HandoffOrchestration orchestration =
            new(Handoffs
                    .StartWith(triageAgent)
                    .Add(triageAgent, [dotnetAgent, pythonAgent]))
            {
                LoggerFactory = this.LoggerFactory,
                ResponseCallback = monitor.ResponseCallbackAsync,
            };

        GithubIssue input =
            new()
            {
                Id = "12345",
                Title = "Bug: SQLite Error 1: 'ambiguous column name:' when including VectorStoreRecordKey in VectorSearchOptions.Filter",
                Body =
                    """
                    Describe the bug
                    When using column names marked as [VectorStoreRecordData(IsFilterable = true)] in VectorSearchOptions.Filter, the query runs correctly.
                    However, using the column name marked as [VectorStoreRecordKey] in VectorSearchOptions.Filter, the query throws exception 'SQLite Error 1: ambiguous column name: StartUTC'.
                    To Reproduce
                    Add a filter for the column marked [VectorStoreRecordKey]. Since that same column exists in both the vec_TestTable and TestTable, the data for both columns cannot be returned.

                    Expected behavior
                    The query should explicitly list the vec_TestTable column names to retrieve and should omit the [VectorStoreRecordKey] column since it will be included in the primary TestTable columns.

                    Platform
                    Microsoft.SemanticKernel.Connectors.Sqlite v1.46.0-preview

                    Additional context
                    Normal DBContext logging shows only normal context queries. Queries run by VectorizedSearchAsync() don't appear in those logs and I could not find a way to enable logging in semantic search so that I could actually see the exact query that is failing. It would have been very useful to see the failing semantic query.                    
                    """,
                Labels = []
            };

        // Run the orchestration
        Console.WriteLine($"\n# INPUT:\n{input.Id}: {input.Title}\n");
        AgentRunResponse result = await orchestration.RunAsync(JsonSerializer.Serialize(input));
        Console.WriteLine($"\n# RESULT: {result}");
        Console.WriteLine($"\n# LABELS: {string.Join(",", githubPlugin.Labels["12345"])}\n");
    }

    private sealed class GithubIssue
    {
        [JsonPropertyName("id")]
        public string Id { get; set; } = string.Empty;

        [JsonPropertyName("title")]
        public string Title { get; set; } = string.Empty;

        [JsonPropertyName("body")]
        public string Body { get; set; } = string.Empty;

        [JsonPropertyName("labels")]
        public string[] Labels { get; set; } = [];
    }

    private sealed class GithubPlugin
    {
        public Dictionary<string, string[]> Labels { get; } = [];

        public void AddLabels(string issueId, params string[] labels) => this.Labels[issueId] = labels;
    }
}
