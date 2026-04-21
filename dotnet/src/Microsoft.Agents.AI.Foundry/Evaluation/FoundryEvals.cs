// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Microsoft.Extensions.AI.Evaluation;
using OpenAI.Evals;

#pragma warning disable OPENAI001 // EvaluationClient is experimental

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Azure AI Foundry evaluator provider that calls the Foundry Evals API.
/// </summary>
/// <remarks>
/// <para>
/// Uses the OpenAI Evals API (<c>evals.create</c> / <c>evals.runs.create</c>) via the
/// project endpoint to run evaluations server-side. All built-in Foundry evaluators
/// (quality, safety, agent behavior, tool usage) are supported.
/// </para>
/// <para>
/// Results appear in the Azure AI Foundry portal with a report URL for detailed analysis.
/// </para>
/// </remarks>
[UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing Dictionary<string, object> for eval API payloads.")]
[UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing Dictionary<string, object> for eval API payloads.")]
public sealed class FoundryEvals : IAgentEvaluator
{
    private static readonly JsonSerializerOptions s_jsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull,
    };

    private readonly EvaluationClient _evaluationClient;
    private readonly string _model;
    private readonly string[] _evaluatorNames;
    private readonly IConversationSplitter? _splitter;
    private readonly double _pollIntervalSeconds = 5.0;
    private readonly double _timeoutSeconds = 300.0;

    // -----------------------------------------------------------------------
    // Constructors
    // -----------------------------------------------------------------------

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryEvals"/> class.
    /// </summary>
    /// <param name="projectClient">The Azure AI Foundry project client.</param>
    /// <param name="model">Model deployment name for the LLM judge evaluator.</param>
    /// <param name="evaluators">
    /// Names of evaluators to use (e.g., <see cref="Relevance"/>, <see cref="Coherence"/>).
    /// When empty, defaults to relevance and coherence.
    /// </param>
    public FoundryEvals(AIProjectClient projectClient, string model, params string[] evaluators)
    {
        ArgumentNullException.ThrowIfNull(projectClient);
        ArgumentException.ThrowIfNullOrWhiteSpace(model);

        this._evaluationClient = projectClient.GetProjectOpenAIClient().GetEvaluationClient();
        this._model = model;
        this._evaluatorNames = evaluators.Length > 0
            ? evaluators
            : [Relevance, Coherence, TaskAdherence];
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryEvals"/> class with a conversation splitter.
    /// </summary>
    /// <param name="projectClient">The Azure AI Foundry project client.</param>
    /// <param name="model">Model deployment name for the LLM judge evaluator.</param>
    /// <param name="splitter">
    /// Default conversation splitter for multi-turn conversations.
    /// Use <see cref="ConversationSplitters.LastTurn"/>, <see cref="ConversationSplitters.Full"/>,
    /// or a custom <see cref="IConversationSplitter"/> implementation.
    /// </param>
    /// <param name="evaluators">
    /// Names of evaluators to use (e.g., <see cref="Relevance"/>, <see cref="Coherence"/>).
    /// When empty, defaults to relevance and coherence.
    /// </param>
    public FoundryEvals(
        AIProjectClient projectClient,
        string model,
        IConversationSplitter? splitter,
        params string[] evaluators)
        : this(projectClient, model, evaluators)
    {
        this._splitter = splitter;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryEvals"/> class with full configuration.
    /// </summary>
    /// <param name="projectClient">The Azure AI Foundry project client.</param>
    /// <param name="model">Model deployment name for the LLM judge evaluator.</param>
    /// <param name="splitter">
    /// Default conversation splitter for multi-turn conversations.
    /// </param>
    /// <param name="pollIntervalSeconds">Seconds between status polls (default 5).</param>
    /// <param name="timeoutSeconds">Maximum seconds to wait for completion (default 300).</param>
    /// <param name="evaluators">Evaluator names to use.</param>
    public FoundryEvals(
        AIProjectClient projectClient,
        string model,
        IConversationSplitter? splitter,
        double pollIntervalSeconds,
        double timeoutSeconds,
        params string[] evaluators)
        : this(projectClient, model, splitter, evaluators)
    {
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(pollIntervalSeconds, 0);
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(timeoutSeconds, 0);
        this._pollIntervalSeconds = pollIntervalSeconds;
        this._timeoutSeconds = timeoutSeconds;
    }

    // -----------------------------------------------------------------------
    // IAgentEvaluator
    // -----------------------------------------------------------------------

    /// <inheritdoc />
    public string Name => "FoundryEvals";

    /// <inheritdoc />
    public async Task<AgentEvaluationResults> EvaluateAsync(
        IReadOnlyList<EvalItem> items,
        string evalName = "Agent Framework Eval",
        CancellationToken cancellationToken = default)
    {
        // 1. Convert EvalItems to typed payloads
        var payloads = new List<WireEvalItemPayload>(items.Count);
        foreach (var item in items)
        {
            payloads.Add(FoundryEvalConverter.ConvertEvalItem(item, this._splitter));
        }

        bool hasContext = payloads.Any(p => p.Context is not null);
        bool hasTools = payloads.Any(p => p.ToolDefinitions is { Count: > 0 });

        // Filter out tool evaluators if no items have tools; auto-add ToolCallAccuracy if tools present
        var evaluators = FilterToolEvaluators(this._evaluatorNames, hasTools);
        if (hasTools && !evaluators.Any(e => FoundryEvalConverter.ToolEvaluators.Contains(FoundryEvalConverter.ResolveEvaluator(e))))
        {
            evaluators = [.. evaluators, ToolCallAccuracy];
        }

        // 2. Create the evaluation definition
        var createEvalPayload = new WireCreateEvalRequest
        {
            Name = evalName,
            DataSourceConfig = new WireCustomDataSourceConfig
            {
                ItemSchema = FoundryEvalConverter.BuildItemSchema(hasContext, hasTools),
            },
            TestingCriteria = FoundryEvalConverter.BuildTestingCriteria(
                evaluators, this._model, includeDataMapping: true),
        };

        var createEvalJson = JsonSerializer.Serialize(createEvalPayload, s_jsonOptions);
        var createEvalResult = await this._evaluationClient.CreateEvaluationAsync(
            BinaryContent.Create(BinaryData.FromString(createEvalJson)),
            new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

        string evalId;
        using (var evalResponse = JsonDocument.Parse(createEvalResult.GetRawResponse().Content))
        {
            evalId = evalResponse.RootElement.GetProperty("id").GetString()
                ?? throw new InvalidOperationException("Foundry eval creation returned a null ID.");
        }

        // 3. Create the evaluation run with inline JSONL data
        var createRunPayload = new WireCreateRunRequest
        {
            Name = $"{evalName} Run",
            DataSource = new WireJsonlDataSource
            {
                Source = new WireFileContentSource
                {
                    Content = payloads.ConvertAll(p => new WireItemWrapper { Item = p }),
                },
            },
        };

        var createRunJson = JsonSerializer.Serialize(createRunPayload, s_jsonOptions);
        var createRunResult = await this._evaluationClient.CreateEvaluationRunAsync(
            evalId,
            BinaryContent.Create(BinaryData.FromString(createRunJson)),
            new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

        string runId;
        using (var runResponse = JsonDocument.Parse(createRunResult.GetRawResponse().Content))
        {
            runId = runResponse.RootElement.GetProperty("id").GetString()
                ?? throw new InvalidOperationException("Foundry eval run creation returned a null run ID.");
        }

        // 4. Poll until complete
        var pollResult = await this.PollEvalRunAsync(evalId, runId, cancellationToken).ConfigureAwait(false);

        if (pollResult.Status is "failed" or "canceled")
        {
            throw new InvalidOperationException(
                $"Foundry evaluation run {runId} {pollResult.Status}: {pollResult.ErrorMessage ?? "no details available"}");
        }

        if (pollResult.Status == "timeout")
        {
            throw new TimeoutException(
                $"Foundry evaluation run {runId} did not complete within {this._timeoutSeconds}s. " +
                "Increase timeoutSeconds or check the run status in the Foundry portal.");
        }

        // 5. Fetch output items and build results
        var fetchResult = await this.FetchOutputItemResultsAsync(evalId, runId, cancellationToken).ConfigureAwait(false);

        // Pad MEAI results if we got fewer than items (e.g. partial output)
        if (fetchResult.MeaiResults.Count < items.Count)
        {
            Trace.TraceWarning(
                "Foundry returned {0} result(s) but {1} item(s) were submitted. " +
                "Padding {2} missing item(s) with empty results — these items will count as failed.",
                fetchResult.MeaiResults.Count,
                items.Count,
                items.Count - fetchResult.MeaiResults.Count);
        }

        while (fetchResult.MeaiResults.Count < items.Count)
        {
            fetchResult.MeaiResults.Add(new EvaluationResult());
        }

        return new AgentEvaluationResults(this.Name, fetchResult.MeaiResults, inputItems: items)
        {
            ReportUrl = pollResult.ReportUrl is not null ? new Uri(pollResult.ReportUrl) : null,
            EvalId = evalId,
            RunId = runId,
            Status = pollResult.Status,
            Error = pollResult.ErrorMessage,
            PerEvaluator = pollResult.PerEvaluator,
            DetailedItems = fetchResult.DetailedItems,
        };
    }

    // -----------------------------------------------------------------------
    // Static evaluation methods (traces and targets)
    // -----------------------------------------------------------------------

    /// <summary>
    /// Evaluates agent behavior from Responses API response IDs, OTel traces, or agent activity.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Foundry-specific method that works with any agent emitting OTel traces to App Insights.
    /// Provide <paramref name="responseIds"/> for specific Responses API responses,
    /// <paramref name="traceIds"/> for specific traces, or <paramref name="agentId"/> with
    /// <paramref name="lookbackHours"/> to evaluate recent activity.
    /// </para>
    /// </remarks>
    /// <param name="projectClient">The Azure AI Foundry project client.</param>
    /// <param name="model">Model deployment name for the LLM judge evaluator.</param>
    /// <param name="responseIds">Evaluate specific Responses API response IDs.</param>
    /// <param name="traceIds">Evaluate specific OTel trace IDs from App Insights.</param>
    /// <param name="agentId">Filter traces by agent ID (used with <paramref name="lookbackHours"/>).</param>
    /// <param name="lookbackHours">Hours of trace history to evaluate (default 24).</param>
    /// <param name="evaluators">Evaluator names. Defaults to relevance, coherence, and task adherence.</param>
    /// <param name="evalName">Display name for the evaluation.</param>
    /// <param name="pollIntervalSeconds">Seconds between status polls (default 5).</param>
    /// <param name="timeoutSeconds">Maximum seconds to wait for completion (default 300).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Evaluation results with status, report URL, and per-item details.</returns>
    public static async Task<AgentEvaluationResults> EvaluateTracesAsync(
        AIProjectClient projectClient,
        string model,
        IEnumerable<string>? responseIds = null,
        IEnumerable<string>? traceIds = null,
        string? agentId = null,
        int lookbackHours = 24,
        string[]? evaluators = null,
        string evalName = "Agent Framework Trace Eval",
        double pollIntervalSeconds = 5.0,
        double timeoutSeconds = 300.0,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(projectClient);
        ArgumentException.ThrowIfNullOrWhiteSpace(model);

        var responseIdList = responseIds?.ToList();
        var traceIdList = traceIds?.ToList();

        if ((responseIdList is null || responseIdList.Count == 0)
            && (traceIdList is null || traceIdList.Count == 0)
            && string.IsNullOrEmpty(agentId))
        {
            throw new ArgumentException("Provide at least one of: responseIds, traceIds, or agentId.");
        }

        var evalClient = projectClient.GetProjectOpenAIClient().GetEvaluationClient();
        var resolvedEvaluators = evaluators is { Length: > 0 }
            ? evaluators
            : [Relevance, Coherence, TaskAdherence];

        // Create the evaluation definition with the appropriate data source scenario
        object dataSourceConfig;
        object runDataSource;

        if (responseIdList is { Count: > 0 })
        {
            // Responses API path
            dataSourceConfig = new WireAzureAiDataSourceConfig { Scenario = "responses" };

            runDataSource = new WireResponsesDataSource
            {
                ItemGenerationParams = new WireResponseRetrievalParams
                {
                    DataMapping = new Dictionary<string, string> { ["response_id"] = "{{item.resp_id}}" },
                    Source = new WireFileContentSource
                    {
                        Content = responseIdList.ConvertAll(id => new WireItemWrapper
                        {
                            Item = new WireResponseIdItem { RespId = id },
                        }),
                    },
                },
            };
        }
        else
        {
            // Traces path
            dataSourceConfig = new WireAzureAiDataSourceConfig { Scenario = "traces" };

            runDataSource = new WireTracesDataSource
            {
                LookbackHours = lookbackHours,
                TraceIds = traceIdList is { Count: > 0 } ? traceIdList : null,
                AgentId = !string.IsNullOrEmpty(agentId) ? agentId : null,
            };
        }

        var createEvalPayload = new WireCreateEvalRequest
        {
            Name = evalName,
            DataSourceConfig = dataSourceConfig,
            TestingCriteria = FoundryEvalConverter.BuildTestingCriteria(resolvedEvaluators, model),
        };

        var createEvalJson = JsonSerializer.Serialize(createEvalPayload, s_jsonOptions);
        var createEvalResult = await evalClient.CreateEvaluationAsync(
            BinaryContent.Create(BinaryData.FromString(createEvalJson)),
            new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

        string evalId;
        using (var evalResponse = JsonDocument.Parse(createEvalResult.GetRawResponse().Content))
        {
            evalId = evalResponse.RootElement.GetProperty("id").GetString()
                ?? throw new InvalidOperationException("Foundry eval creation returned a null ID.");
        }

        var createRunPayload = new WireCreateRunRequest
        {
            Name = $"{evalName} Run",
            DataSource = runDataSource,
        };

        var createRunJson = JsonSerializer.Serialize(createRunPayload, s_jsonOptions);
        var createRunResult = await evalClient.CreateEvaluationRunAsync(
            evalId,
            BinaryContent.Create(BinaryData.FromString(createRunJson)),
            new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

        string runId;
        using (var runResponse = JsonDocument.Parse(createRunResult.GetRawResponse().Content))
        {
            runId = runResponse.RootElement.GetProperty("id").GetString()
                ?? throw new InvalidOperationException("Foundry eval run creation returned a null run ID.");
        }

        // Poll and fetch
        var instance = new FoundryEvals(projectClient, model, null, pollIntervalSeconds, timeoutSeconds, resolvedEvaluators);
        var pollResult = await instance.PollEvalRunAsync(evalId, runId, cancellationToken).ConfigureAwait(false);

        if (pollResult.Status is "failed" or "canceled")
        {
            throw new InvalidOperationException(
                $"Foundry trace evaluation run {runId} {pollResult.Status}: {pollResult.ErrorMessage ?? "no details available"}");
        }

        if (pollResult.Status == "timeout")
        {
            throw new TimeoutException(
                $"Foundry trace evaluation run {runId} did not complete within {timeoutSeconds}s.");
        }

        var fetchResult = await instance.FetchOutputItemResultsAsync(evalId, runId, cancellationToken).ConfigureAwait(false);

        return new AgentEvaluationResults("FoundryEvals", fetchResult.MeaiResults)
        {
            ReportUrl = pollResult.ReportUrl is not null ? new Uri(pollResult.ReportUrl) : null,
            EvalId = evalId,
            RunId = runId,
            Status = pollResult.Status,
            Error = pollResult.ErrorMessage,
            PerEvaluator = pollResult.PerEvaluator,
            DetailedItems = fetchResult.DetailedItems,
        };
    }

    /// <summary>
    /// Evaluates a Foundry-registered agent or model deployment.
    /// </summary>
    /// <remarks>
    /// Foundry invokes the target, captures the output, and evaluates it.
    /// Use this for scheduled evaluations, red teaming, and CI/CD quality gates.
    /// </remarks>
    /// <param name="projectClient">The Azure AI Foundry project client.</param>
    /// <param name="model">Model deployment name for the LLM judge evaluator.</param>
    /// <param name="target">Target configuration (must include a "type" key, e.g. "azure_ai_agent").</param>
    /// <param name="testQueries">Queries for Foundry to send to the target.</param>
    /// <param name="evaluators">Evaluator names. Defaults to relevance, coherence, and task adherence.</param>
    /// <param name="evalName">Display name for the evaluation.</param>
    /// <param name="pollIntervalSeconds">Seconds between status polls (default 5).</param>
    /// <param name="timeoutSeconds">Maximum seconds to wait for completion (default 300).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Evaluation results with status, report URL, and per-item details.</returns>
    public static async Task<AgentEvaluationResults> EvaluateFoundryTargetAsync(
        AIProjectClient projectClient,
        string model,
        IDictionary<string, object> target,
        IEnumerable<string> testQueries,
        string[]? evaluators = null,
        string evalName = "Agent Framework Target Eval",
        double pollIntervalSeconds = 5.0,
        double timeoutSeconds = 300.0,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(projectClient);
        ArgumentException.ThrowIfNullOrWhiteSpace(model);
        ArgumentNullException.ThrowIfNull(target);

        if (!target.ContainsKey("type"))
        {
            throw new ArgumentException("Target must include a 'type' key (e.g., 'azure_ai_agent').", nameof(target));
        }

        var queryList = testQueries.ToList();
        if (queryList.Count == 0)
        {
            throw new ArgumentException("At least one test query is required.", nameof(testQueries));
        }

        var evalClient = projectClient.GetProjectOpenAIClient().GetEvaluationClient();
        var resolvedEvaluators = evaluators is { Length: > 0 }
            ? evaluators
            : [Relevance, Coherence, TaskAdherence];

        var createEvalPayload = new WireCreateEvalRequest
        {
            Name = evalName,
            DataSourceConfig = new WireAzureAiDataSourceConfig { Scenario = "target_completions" },
            TestingCriteria = FoundryEvalConverter.BuildTestingCriteria(resolvedEvaluators, model),
        };

        var createEvalJson = JsonSerializer.Serialize(createEvalPayload, s_jsonOptions);
        var createEvalResult = await evalClient.CreateEvaluationAsync(
            BinaryContent.Create(BinaryData.FromString(createEvalJson)),
            new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

        string evalId;
        using (var evalResponse = JsonDocument.Parse(createEvalResult.GetRawResponse().Content))
        {
            evalId = evalResponse.RootElement.GetProperty("id").GetString()
                ?? throw new InvalidOperationException("Foundry eval creation returned a null ID.");
        }

        var createRunPayload = new WireCreateRunRequest
        {
            Name = $"{evalName} Run",
            DataSource = new WireTargetCompletionsDataSource
            {
                Target = target,
                Source = new WireFileContentSource
                {
                    Content = queryList.ConvertAll(q => new WireItemWrapper
                    {
                        Item = new WireQueryItem { Query = q },
                    }),
                },
            },
        };

        var createRunJson = JsonSerializer.Serialize(createRunPayload, s_jsonOptions);
        var createRunResult = await evalClient.CreateEvaluationRunAsync(
            evalId,
            BinaryContent.Create(BinaryData.FromString(createRunJson)),
            new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

        string runId;
        using (var runResponse = JsonDocument.Parse(createRunResult.GetRawResponse().Content))
        {
            runId = runResponse.RootElement.GetProperty("id").GetString()
                ?? throw new InvalidOperationException("Foundry eval run creation returned a null run ID.");
        }

        var instance = new FoundryEvals(projectClient, model, null, pollIntervalSeconds, timeoutSeconds, resolvedEvaluators);
        var pollResult = await instance.PollEvalRunAsync(evalId, runId, cancellationToken).ConfigureAwait(false);

        if (pollResult.Status is "failed" or "canceled")
        {
            throw new InvalidOperationException(
                $"Foundry target evaluation run {runId} {pollResult.Status}: {pollResult.ErrorMessage ?? "no details available"}");
        }

        if (pollResult.Status == "timeout")
        {
            throw new TimeoutException(
                $"Foundry target evaluation run {runId} did not complete within {timeoutSeconds}s.");
        }

        var fetchResult = await instance.FetchOutputItemResultsAsync(evalId, runId, cancellationToken).ConfigureAwait(false);

        return new AgentEvaluationResults("FoundryEvals", fetchResult.MeaiResults)
        {
            ReportUrl = pollResult.ReportUrl is not null ? new Uri(pollResult.ReportUrl) : null,
            EvalId = evalId,
            RunId = runId,
            Status = pollResult.Status,
            Error = pollResult.ErrorMessage,
            PerEvaluator = pollResult.PerEvaluator,
            DetailedItems = fetchResult.DetailedItems,
        };
    }

    // -----------------------------------------------------------------------
    // Evaluator name constants
    // -----------------------------------------------------------------------

    // Agent behavior

    /// <summary>Evaluates whether the agent correctly resolves user intent.</summary>
    public const string IntentResolution = "intent_resolution";

    /// <summary>Evaluates whether the agent adheres to its task instructions.</summary>
    public const string TaskAdherence = "task_adherence";

    /// <summary>Evaluates whether the agent completes the requested task.</summary>
    public const string TaskCompletion = "task_completion";

    /// <summary>Evaluates the efficiency of the agent's navigation to complete the task.</summary>
    public const string TaskNavigationEfficiency = "task_navigation_efficiency";

    // Tool usage

    /// <summary>Evaluates the accuracy of tool calls made by the agent.</summary>
    public const string ToolCallAccuracy = "tool_call_accuracy";

    /// <summary>Evaluates whether the agent selects the correct tools.</summary>
    public const string ToolSelection = "tool_selection";

    /// <summary>Evaluates the accuracy of inputs provided to tools.</summary>
    public const string ToolInputAccuracy = "tool_input_accuracy";

    /// <summary>Evaluates how well the agent uses tool outputs.</summary>
    public const string ToolOutputUtilization = "tool_output_utilization";

    /// <summary>Evaluates whether tool calls succeed.</summary>
    public const string ToolCallSuccess = "tool_call_success";

    // Quality

    /// <summary>Evaluates the coherence of the response.</summary>
    public const string Coherence = "coherence";

    /// <summary>Evaluates the fluency of the response.</summary>
    public const string Fluency = "fluency";

    /// <summary>Evaluates the relevance of the response to the query.</summary>
    public const string Relevance = "relevance";

    /// <summary>Evaluates whether the response is grounded in the provided context.</summary>
    public const string Groundedness = "groundedness";

    /// <summary>Evaluates the completeness of the response.</summary>
    public const string ResponseCompleteness = "response_completeness";

    /// <summary>Evaluates the similarity between the response and the expected output.</summary>
    public const string Similarity = "similarity";

    // Safety

    /// <summary>Evaluates the response for violent content.</summary>
    public const string Violence = "violence";

    /// <summary>Evaluates the response for sexual content.</summary>
    public const string Sexual = "sexual";

    /// <summary>Evaluates the response for self-harm content.</summary>
    public const string SelfHarm = "self_harm";

    /// <summary>Evaluates the response for hate or unfairness.</summary>
    public const string HateUnfairness = "hate_unfairness";

    // -----------------------------------------------------------------------
    // Internal helpers
    // -----------------------------------------------------------------------

    private async Task<PollResult> PollEvalRunAsync(
        string evalId,
        string runId,
        CancellationToken cancellationToken)
    {
        var deadline = DateTime.UtcNow.AddSeconds(this._timeoutSeconds);

        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var result = await this._evaluationClient.GetEvaluationRunAsync(
                evalId,
                runId,
                new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

            using var runDoc = JsonDocument.Parse(result.GetRawResponse().Content);
            var root = runDoc.RootElement;
            var status = root.GetProperty("status").GetString()!;

            if (status is "completed" or "failed" or "canceled")
            {
                string? reportUrl = root.TryGetProperty("report_url", out var urlProp) ? urlProp.GetString() : null;
                string? errorMessage = root.TryGetProperty("error", out var errProp) ? errProp.ToString() : null;

                // Extract per-evaluator breakdown
                Dictionary<string, PerEvaluatorResult>? perEvaluator = null;
                if (root.TryGetProperty("per_testing_criteria_results", out var criteriaArray)
                    && criteriaArray.ValueKind == JsonValueKind.Array)
                {
                    perEvaluator = new Dictionary<string, PerEvaluatorResult>();
                    foreach (var item in criteriaArray.EnumerateArray())
                    {
                        var name = item.TryGetProperty("testing_criteria", out var tcProp)
                            ? tcProp.GetString()
                            : null;
                        if (name is not null)
                        {
                            int passed = item.TryGetProperty("passed", out var pp) && pp.ValueKind == JsonValueKind.Number
                                ? pp.GetInt32() : 0;
                            int failed = item.TryGetProperty("failed", out var fp) && fp.ValueKind == JsonValueKind.Number
                                ? fp.GetInt32() : 0;
                            perEvaluator[name] = new PerEvaluatorResult(passed, failed);
                        }
                    }
                }

                return new PollResult(status, reportUrl, errorMessage, perEvaluator);
            }

            if (DateTime.UtcNow >= deadline)
            {
                return new PollResult("timeout", null, null, null);
            }

            await Task.Delay(TimeSpan.FromSeconds(this._pollIntervalSeconds), cancellationToken).ConfigureAwait(false);
        }
    }

    private sealed record PollResult(
        string Status,
        string? ReportUrl,
        string? ErrorMessage,
        Dictionary<string, PerEvaluatorResult>? PerEvaluator);

    private async Task<FetchResult> FetchOutputItemResultsAsync(
        string evalId,
        string runId,
        CancellationToken cancellationToken)
    {
        var meaiResults = new List<EvaluationResult>();
        var detailedItems = new List<EvalItemResult>();
        string? afterCursor = null;

        while (true)
        {
            var response = await this._evaluationClient.GetEvaluationRunOutputItemsAsync(
                evalId,
                runId,
                limit: 100,
                order: null,
                after: afterCursor,
                outputItemStatus: null,
                new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

            using var doc = JsonDocument.Parse(response.GetRawResponse().Content);

            if (doc.RootElement.TryGetProperty("data", out var dataArray))
            {
                foreach (var outputItem in dataArray.EnumerateArray())
                {
                    meaiResults.Add(ParseOutputItem(outputItem));
                    detailedItems.Add(ParseDetailedItem(outputItem));
                }
            }

            // Check for more pages
            bool hasMore = doc.RootElement.TryGetProperty("has_more", out var hasMoreProp)
                && hasMoreProp.ValueKind == JsonValueKind.True;

            if (!hasMore)
            {
                break;
            }

            // Get cursor for next page — use last_id or last item's id
            if (doc.RootElement.TryGetProperty("last_id", out var lastIdProp))
            {
                afterCursor = lastIdProp.GetString();
            }
            else if (doc.RootElement.TryGetProperty("data", out var data2) && data2.GetArrayLength() > 0)
            {
                var lastItem = data2[data2.GetArrayLength() - 1];
                afterCursor = lastItem.TryGetProperty("id", out var idProp) ? idProp.GetString() : null;
            }

            if (afterCursor is null)
            {
                break;
            }
        }

        return new FetchResult(meaiResults, detailedItems);
    }

    private sealed record FetchResult(
        List<EvaluationResult> MeaiResults,
        List<EvalItemResult> DetailedItems);

    private static EvaluationResult ParseOutputItem(JsonElement outputItem)
    {
        var evalResult = new EvaluationResult();

        if (outputItem.TryGetProperty("results", out var itemResults))
        {
            foreach (var r in itemResults.EnumerateArray())
            {
                var metricName = r.TryGetProperty("name", out var nameProp)
                    ? nameProp.GetString() ?? "unknown"
                    : "unknown";

                bool? passed = null;
                if (r.TryGetProperty("passed", out var passedProp)
                    && passedProp.ValueKind is JsonValueKind.True or JsonValueKind.False)
                {
                    passed = passedProp.ValueKind == JsonValueKind.True;
                }

                double? score = r.TryGetProperty("score", out var scoreProp) && scoreProp.ValueKind == JsonValueKind.Number
                    ? scoreProp.GetDouble()
                    : null;

                EvaluationMetricInterpretation? interpretation = passed.HasValue
                    ? new EvaluationMetricInterpretation
                    {
                        Rating = passed.Value ? EvaluationRating.Good : EvaluationRating.Unacceptable,
                        Failed = !passed.Value,
                    }
                    : null;

                if (score.HasValue)
                {
                    evalResult.Metrics[metricName] = new NumericMetric(metricName, score.Value)
                    {
                        Interpretation = interpretation,
                    };
                }
                else if (passed.HasValue)
                {
                    evalResult.Metrics[metricName] = new BooleanMetric(metricName, passed.Value)
                    {
                        Interpretation = interpretation,
                    };
                }

                // When neither score nor passed is present, the evaluator returned no
                // actionable data (e.g. an error or informational entry). Skip the metric
                // so it doesn't falsely influence ItemPassed. The raw data is still
                // available in DetailedItems for diagnostics.
            }
        }

        return evalResult;
    }

    private static EvalItemResult ParseDetailedItem(JsonElement outputItem)
    {
        var itemId = outputItem.TryGetProperty("id", out var idProp) ? idProp.GetString() ?? "" : "";
        var status = outputItem.TryGetProperty("status", out var statusProp) ? statusProp.GetString() ?? "" : "";

        var scores = new List<EvalScoreResult>();
        if (outputItem.TryGetProperty("results", out var itemResults))
        {
            foreach (var r in itemResults.EnumerateArray())
            {
                var name = r.TryGetProperty("name", out var np) ? np.GetString() ?? "unknown" : "unknown";
                double score = r.TryGetProperty("score", out var sp) && sp.ValueKind == JsonValueKind.Number
                    ? sp.GetDouble() : 0.0;
                bool? passed = null;
                if (r.TryGetProperty("passed", out var pp) && pp.ValueKind is JsonValueKind.True or JsonValueKind.False)
                {
                    passed = pp.ValueKind == JsonValueKind.True;
                }

                scores.Add(new EvalScoreResult(name, score, passed));
            }
        }

        var result = new EvalItemResult(itemId, status, scores);

        // Extract error info from sample
        if (outputItem.TryGetProperty("sample", out var sample))
        {
            if (sample.TryGetProperty("error", out var errObj))
            {
                result.ErrorCode = errObj.TryGetProperty("code", out var code) ? code.GetString() : null;
                result.ErrorMessage = errObj.TryGetProperty("message", out var msg) ? msg.GetString() : null;
            }

            if (sample.TryGetProperty("usage", out var usage) && usage.TryGetProperty("total_tokens", out var tt) && tt.ValueKind == JsonValueKind.Number)
            {
                var tokenUsage = new Dictionary<string, int>();
                if (usage.TryGetProperty("prompt_tokens", out var pt) && pt.ValueKind == JsonValueKind.Number)
                {
                    tokenUsage["prompt_tokens"] = pt.GetInt32();
                }

                if (usage.TryGetProperty("completion_tokens", out var ct) && ct.ValueKind == JsonValueKind.Number)
                {
                    tokenUsage["completion_tokens"] = ct.GetInt32();
                }

                tokenUsage["total_tokens"] = tt.GetInt32();
                result.TokenUsage = tokenUsage;
            }

            // Extract input/output text
            if (sample.TryGetProperty("input", out var inputArr) && inputArr.ValueKind == JsonValueKind.Array)
            {
                var parts = new List<string>();
                foreach (var si in inputArr.EnumerateArray())
                {
                    if (si.TryGetProperty("role", out var role) && role.GetString() == "user"
                        && si.TryGetProperty("content", out var content))
                    {
                        parts.Add(content.GetString() ?? "");
                    }
                }

                if (parts.Count > 0)
                {
                    result.InputText = string.Join(" ", parts);
                }
            }

            if (sample.TryGetProperty("output", out var outputArr) && outputArr.ValueKind == JsonValueKind.Array)
            {
                var parts = new List<string>();
                foreach (var so in outputArr.EnumerateArray())
                {
                    if (so.TryGetProperty("role", out var role) && role.GetString() == "assistant"
                        && so.TryGetProperty("content", out var content))
                    {
                        parts.Add(content.GetString() ?? "");
                    }
                }

                if (parts.Count > 0)
                {
                    result.OutputText = string.Join(" ", parts);
                }
            }
        }

        // Extract response_id from datasource_item
        if (outputItem.TryGetProperty("datasource_item", out var dsItem))
        {
            if (dsItem.TryGetProperty("resp_id", out var respId))
            {
                result.ResponseId = respId.GetString();
            }
            else if (dsItem.TryGetProperty("response_id", out var responseId))
            {
                result.ResponseId = responseId.GetString();
            }
        }

        return result;
    }

    internal static string[] FilterToolEvaluators(string[] evaluators, bool hasTools)
    {
        if (hasTools)
        {
            return evaluators;
        }

        var filtered = Array.FindAll(evaluators, e =>
            !FoundryEvalConverter.ToolEvaluators.Contains(FoundryEvalConverter.ResolveEvaluator(e)));

        return filtered.Length > 0
            ? filtered
            : throw new ArgumentException(
                "All configured evaluators require tool definitions, but no tool calls were found in the eval items. "
                + $"Tool evaluators: {string.Join(", ", evaluators)}. Either add tool call content to your EvalItems or remove tool-type evaluators.");
    }
}
