// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Evaluation;
using Microsoft.Extensions.AI.Evaluation.Quality;
using Microsoft.Extensions.AI.Evaluation.Safety;

namespace Microsoft.Agents.AI.AzureAI;

/// <summary>
/// Azure AI Foundry evaluator provider with built-in evaluator name constants.
/// </summary>
/// <remarks>
/// <para>
/// Combines evaluator constants (e.g., <see cref="Relevance"/>, <see cref="Coherence"/>)
/// with the <see cref="IAgentEvaluator"/> implementation that maps them to MEAI evaluators.
/// </para>
/// <para>
/// When the Azure.AI.Projects .NET SDK adds native evaluation API support, this class
/// will be updated to use it for full parity with the Python <c>FoundryEvals</c> class.
/// </para>
/// </remarks>
public sealed class FoundryEvals : IAgentEvaluator
{
    private readonly ChatConfiguration _chatConfiguration;
    private readonly string[] _evaluatorNames;
    private readonly IConversationSplitter? _splitter;

    // -----------------------------------------------------------------------
    // Constructors
    // -----------------------------------------------------------------------

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryEvals"/> class.
    /// </summary>
    /// <param name="chatConfiguration">Chat configuration for the LLM-based evaluators.</param>
    /// <param name="evaluators">
    /// Names of evaluators to use (e.g., <see cref="Relevance"/>, <see cref="Coherence"/>).
    /// When empty, defaults to relevance and coherence.
    /// </param>
    public FoundryEvals(ChatConfiguration chatConfiguration, params string[] evaluators)
        : this(chatConfiguration, splitter: null, evaluators)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryEvals"/> class with a default splitter.
    /// </summary>
    /// <param name="chatConfiguration">Chat configuration for the LLM-based evaluators.</param>
    /// <param name="splitter">
    /// Default conversation splitter for multi-turn conversations. Overridden by
    /// <see cref="EvalItem.Splitter"/> when set on individual items.
    /// Use <see cref="ConversationSplitters.LastTurn"/>, <see cref="ConversationSplitters.Full"/>,
    /// or a custom <see cref="IConversationSplitter"/> implementation.
    /// </param>
    /// <param name="evaluators">
    /// Names of evaluators to use (e.g., <see cref="Relevance"/>, <see cref="Coherence"/>).
    /// When empty, defaults to relevance and coherence.
    /// </param>
    public FoundryEvals(ChatConfiguration chatConfiguration, IConversationSplitter? splitter, params string[] evaluators)
    {
        this._chatConfiguration = chatConfiguration;
        this._splitter = splitter;
        this._evaluatorNames = evaluators.Length > 0
            ? evaluators
            : [Relevance, Coherence];
    }

    // -----------------------------------------------------------------------
    // IAgentEvaluator
    // -----------------------------------------------------------------------

    /// <inheritdoc />
    public string Name => "FoundryEvals";

    /// <inheritdoc />
    public async Task<AgentEvaluationResults> EvaluateAsync(
        IReadOnlyList<EvalItem> items,
        string evalName = "Foundry Eval",
        CancellationToken cancellationToken = default)
    {
        var meaiEvaluators = BuildEvaluators(this._evaluatorNames);
        var composite = new CompositeEvaluator(meaiEvaluators.ToArray());

        var results = new List<EvaluationResult>(items.Count);

        foreach (var item in items)
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Resolve splitter: item-level > evaluator-level > LastTurn default
            var effectiveSplitter = item.Splitter ?? this._splitter;
            var (queryMessages, _) = item.Split(effectiveSplitter);
            var messages = queryMessages.ToList();

            var chatResponse = item.RawResponse
                ?? new ChatResponse(new ChatMessage(ChatRole.Assistant, item.Response));

            var additionalContext = new List<EvaluationContext>();

            if (item.Context is not null)
            {
                additionalContext.Add(new GroundednessEvaluatorContext(item.Context));
            }

            var result = await composite.EvaluateAsync(
                messages,
                chatResponse,
                this._chatConfiguration,
                additionalContext: additionalContext.Count > 0 ? additionalContext : null,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            results.Add(result);
        }

        return new AgentEvaluationResults(this.Name, results);
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

    internal static List<IEvaluator> BuildEvaluators(string[] names)
    {
        var evaluators = new List<IEvaluator>();
        bool hasSafetyEvaluator = false;

        foreach (var name in names)
        {
            IEvaluator? evaluator = name switch
            {
                Relevance => new RelevanceEvaluator(),
                Coherence => new CoherenceEvaluator(),
                Groundedness => new GroundednessEvaluator(),
                Fluency => new FluencyEvaluator(),

                // ContentHarmEvaluator covers all harm categories in one call — deduplicate
                Violence or
                Sexual or
                SelfHarm or
                HateUnfairness when !hasSafetyEvaluator => new ContentHarmEvaluator(),

                Violence or
                Sexual or
                SelfHarm or
                HateUnfairness => null,

                _ => throw new ArgumentException(
                    $"Evaluator '{name}' is not supported by the .NET FoundryEvals adapter. " +
                    $"Supported: {Relevance}, {Coherence}, {Groundedness}, {Fluency}, " +
                    $"{Violence}, {Sexual}, {SelfHarm}, {HateUnfairness}.",
                    nameof(names)),
            };

            if (evaluator is ContentHarmEvaluator)
            {
                hasSafetyEvaluator = true;
            }

            if (evaluator is not null)
            {
                evaluators.Add(evaluator);
            }
        }

        return evaluators;
    }
}
