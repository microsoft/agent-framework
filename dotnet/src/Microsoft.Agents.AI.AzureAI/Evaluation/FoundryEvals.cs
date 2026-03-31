// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Azure.AI.Projects;
using Microsoft.Extensions.AI.Evaluation;
using OpenAI.Evals;

#pragma warning disable OPENAI001 // EvaluationClient is experimental

namespace Microsoft.Agents.AI.AzureAI;

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
            : [Relevance, Coherence];
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
    /// <param name="timeoutSeconds">Maximum seconds to wait for completion (default 180).</param>
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
        // 1. Convert EvalItems to JSONL dicts
        var dicts = new List<Dictionary<string, object>>(items.Count);
        foreach (var item in items)
        {
            dicts.Add(FoundryEvalConverter.ConvertEvalItem(item, this._splitter));
        }

        bool hasContext = dicts.Any(d => d.ContainsKey("context"));
        bool hasTools = dicts.Any(d => d.ContainsKey("tool_definitions"));

        // Filter out tool evaluators if no items have tools
        var evaluators = FilterToolEvaluators(this._evaluatorNames, hasTools);

        // 2. Create the evaluation definition
        var createEvalPayload = new Dictionary<string, object>
        {
            ["name"] = evalName,
            ["data_source_config"] = new Dictionary<string, object>
            {
                ["type"] = "custom",
                ["item_schema"] = FoundryEvalConverter.BuildItemSchema(hasContext, hasTools),
                ["include_sample_schema"] = true,
            },
            ["testing_criteria"] = FoundryEvalConverter.BuildTestingCriteria(
                evaluators, this._model, includeDataMapping: true),
        };

        var createEvalJson = JsonSerializer.Serialize(createEvalPayload, s_jsonOptions);
        var createEvalResult = await this._evaluationClient.CreateEvaluationAsync(
            BinaryContent.Create(BinaryData.FromString(createEvalJson)),
            new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

        string evalId;
        using (var evalResponse = JsonDocument.Parse(createEvalResult.GetRawResponse().Content))
        {
            evalId = evalResponse.RootElement.GetProperty("id").GetString()!;
        }

        // 3. Create the evaluation run with inline JSONL data
        var dataSource = new Dictionary<string, object>
        {
            ["type"] = "jsonl",
            ["source"] = new Dictionary<string, object>
            {
                ["type"] = "file_content",
                ["content"] = dicts.ConvertAll(d => (object)new Dictionary<string, object> { ["item"] = d }),
            },
        };

        var createRunPayload = new Dictionary<string, object>
        {
            ["name"] = $"{evalName} Run",
            ["data_source"] = dataSource,
        };

        var createRunJson = JsonSerializer.Serialize(createRunPayload, s_jsonOptions);
        var createRunResult = await this._evaluationClient.CreateEvaluationRunAsync(
            evalId,
            BinaryContent.Create(BinaryData.FromString(createRunJson)),
            new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

        string runId;
        using (var runResponse = JsonDocument.Parse(createRunResult.GetRawResponse().Content))
        {
            runId = runResponse.RootElement.GetProperty("id").GetString()!;
        }

        // 4. Poll until complete
        var (status, reportUrl, errorMessage) = await this.PollEvalRunAsync(evalId, runId, cancellationToken).ConfigureAwait(false);

        if (status is "failed" or "canceled")
        {
            throw new InvalidOperationException(
                $"Foundry evaluation run {runId} {status}: {errorMessage ?? "no details available"}");
        }

        if (status == "timeout")
        {
            throw new TimeoutException(
                $"Foundry evaluation run {runId} did not complete within {this._timeoutSeconds}s. " +
                "Increase timeoutSeconds or check the run status in the Foundry portal.");
        }

        // 5. Fetch output items and build results
        var evalResults = await this.FetchOutputItemResultsAsync(evalId, runId, cancellationToken).ConfigureAwait(false);

        // Pad results if we got fewer than items (e.g. partial output)
        while (evalResults.Count < items.Count)
        {
            evalResults.Add(new EvaluationResult());
        }

        return new AgentEvaluationResults(this.Name, evalResults, inputItems: items)
        {
            ReportUrl = reportUrl is not null ? new Uri(reportUrl) : null,
            EvalId = evalId,
            RunId = runId,
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

    private async Task<(string Status, string? ReportUrl, string? ErrorMessage)> PollEvalRunAsync(
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
                return (status, reportUrl, errorMessage);
            }

            if (DateTime.UtcNow >= deadline)
            {
                return ("timeout", null, null);
            }

            await Task.Delay(TimeSpan.FromSeconds(this._pollIntervalSeconds), cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task<List<EvaluationResult>> FetchOutputItemResultsAsync(
        string evalId,
        string runId,
        CancellationToken cancellationToken)
    {
        var results = new List<EvaluationResult>();

        var response = await this._evaluationClient.GetEvaluationRunOutputItemsAsync(
            evalId,
            runId,
            limit: null,
            order: null,
            after: null,
            outputItemStatus: null,
            new RequestOptions { CancellationToken = cancellationToken }).ConfigureAwait(false);

        using var doc = JsonDocument.Parse(response.GetRawResponse().Content);
        if (doc.RootElement.TryGetProperty("data", out var dataArray))
        {
            foreach (var outputItem in dataArray.EnumerateArray())
            {
                var evalResult = new EvaluationResult();

                if (outputItem.TryGetProperty("results", out var itemResults))
                {
                    foreach (var r in itemResults.EnumerateArray())
                    {
                        var metricName = r.TryGetProperty("name", out var nameProp)
                            ? nameProp.GetString() ?? "unknown"
                            : "unknown";

                        bool? passed = r.TryGetProperty("passed", out var passedProp) && passedProp.ValueKind == JsonValueKind.True
                            ? true
                            : r.TryGetProperty("passed", out var passedProp2) && passedProp2.ValueKind == JsonValueKind.False
                                ? false
                                : null;

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
                        else
                        {
                            evalResult.Metrics[metricName] = new BooleanMetric(metricName, passed ?? false)
                            {
                                Interpretation = interpretation,
                            };
                        }
                    }
                }

                results.Add(evalResult);
            }
        }

        return results;
    }

    private static string[] FilterToolEvaluators(string[] evaluators, bool hasTools)
    {
        if (hasTools)
        {
            return evaluators;
        }

        var filtered = Array.FindAll(evaluators, e =>
            !FoundryEvalConverter.ToolEvaluators.Contains(FoundryEvalConverter.ResolveEvaluator(e)));

        return filtered.Length > 0 ? filtered : evaluators;
    }
}
