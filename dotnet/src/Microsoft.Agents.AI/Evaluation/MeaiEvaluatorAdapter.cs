// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Evaluation;

namespace Microsoft.Agents.AI;

/// <summary>
/// Adapter that wraps an MEAI <see cref="IEvaluator"/> into an <see cref="IAgentEvaluator"/>.
/// Runs the MEAI evaluator per-item and aggregates results.
/// </summary>
internal sealed class MeaiEvaluatorAdapter : IAgentEvaluator
{
    private readonly IEvaluator _evaluator;
    private readonly ChatConfiguration _chatConfiguration;

    /// <summary>
    /// Initializes a new instance of the <see cref="MeaiEvaluatorAdapter"/> class.
    /// </summary>
    /// <param name="evaluator">The MEAI evaluator to wrap.</param>
    /// <param name="chatConfiguration">Chat configuration for the evaluator (includes the judge model).</param>
    public MeaiEvaluatorAdapter(IEvaluator evaluator, ChatConfiguration chatConfiguration)
    {
        this._evaluator = evaluator;
        this._chatConfiguration = chatConfiguration;
    }

    /// <inheritdoc />
    public string Name => this._evaluator.GetType().Name;

    /// <inheritdoc />
    public async Task<AgentEvaluationResults> EvaluateAsync(
        IReadOnlyList<EvalItem> items,
        string evalName = "MEAI Eval",
        CancellationToken cancellationToken = default)
    {
        var results = new List<EvaluationResult>(items.Count);

        foreach (var item in items)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var (queryMessages, _) = item.Split();
            var messages = queryMessages.ToList();
            var chatResponse = item.RawResponse
                ?? new ChatResponse(new ChatMessage(ChatRole.Assistant, item.Response));

            var result = await this._evaluator.EvaluateAsync(
                messages,
                chatResponse,
                this._chatConfiguration,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            results.Add(result);
        }

        return new AgentEvaluationResults(this.Name, results, inputItems: items);
    }
}
