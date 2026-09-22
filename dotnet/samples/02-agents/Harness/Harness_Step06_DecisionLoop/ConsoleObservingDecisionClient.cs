// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable MAAI001 // Suppress experimental API warnings for Agents AI experiments.

using System.Text.Json;
using Microsoft.Agents.AI;

namespace Harness_Step06_DecisionLoop;

/// <summary>
/// A delegating <see cref="IDecisionClient"/> that prints every binary answer it sees, so the loop's decisions are
/// visible on the console. It is the decision-model counterpart of a logging chat client: the same shape works for
/// shadow-mode recording, calibration capture, or metrics.
/// </summary>
internal sealed class ConsoleObservingDecisionClient(IDecisionClient inner) : IDecisionClient
{
    public async Task<DecisionResponse> GetResponseAsync(DecisionRequest request, DecisionOptions? options = null, CancellationToken cancellationToken = default)
    {
        DecisionResponse response = await inner.GetResponseAsync(request, options, cancellationToken);

        int iteration = request.State.ValueKind == JsonValueKind.Object && request.State.TryGetProperty("iteration", out JsonElement it) ? it.GetInt32() : 0;
        foreach (DecisionQuestion question in request.Questions)
        {
            if (response.Answers.TryGetValue(question.Id, out DecisionAnswer? answer) && answer is BinaryDecisionAnswer binary && iteration > 0)
            {
                Console.WriteLine($"\n  [Jev] iteration {iteration}: P({question.Id}) = {binary.TrueProbability:F3} (model {response.ModelId}, {response.Usage?.InputTokenCount} input tokens)");
            }
        }

        return response;
    }

    public object? GetService(Type serviceType, object? serviceKey = null) =>
        serviceKey is null && serviceType.IsInstanceOfType(this) ? this : inner.GetService(serviceType, serviceKey);

    public void Dispose() => inner.Dispose();
}
