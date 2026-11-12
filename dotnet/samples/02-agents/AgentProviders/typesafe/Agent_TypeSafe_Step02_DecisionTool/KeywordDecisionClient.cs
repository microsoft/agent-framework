// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable MEAI001 // The decision API is experimental.

using System.Text.RegularExpressions;
using Microsoft.Extensions.AI;

/// <summary>
/// A local <see cref="IDecisionClient"/> that answers by matching words, as a stand-in for another decision model.
/// </summary>
/// <remarks>
/// It knows only this sample's questions: a Choice picks the candidate whose description shares the most words with the
/// ticket, a Binary question looks for urgent words, and a Score counts frustrated words. Like any decision client, it
/// answers every question with a complete distribution.
/// </remarks>
internal sealed partial class KeywordDecisionClient : IDecisionClient
{
    private static readonly string[] s_urgentWords = ["asap", "urgent", "immediately", "losing", "down", "blocked"];
    private static readonly string[] s_frustratedWords = ["still", "keeps", "again", "losing", "days", "failing"];

    public Task<DecisionResponse> GetResponseAsync(DecisionRequest request, DecisionOptions? options = null, CancellationToken cancellationToken = default)
    {
        HashSet<string> words = Stems(request.State.GetRawText());
        List<DecisionAnswer> answers = [.. request.Questions.Select(question => Answer(question, words))];
        return Task.FromResult(new DecisionResponse(request, answers, new DecisionProvenance(providerName: "local", modelId: "local-keyword-matcher")));
    }

    public object? GetService(Type serviceType, object? serviceKey = null) =>
        serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;

    public void Dispose()
    {
    }

    private static DecisionAnswer Answer(DecisionQuestion question, HashSet<string> words) =>
        question switch
        {
            ChoiceDecisionQuestion choice => Choose(choice, words),
            BinaryDecisionQuestion binary => new BinaryDecisionAnswer(binary.Id, s_urgentWords.Any(word => words.Contains(Stem(word))) ? 0.9 : 0.1),
            ScoreDecisionQuestion score => Rate(score, words),
            _ => throw new NotSupportedException($"The keyword client does not answer {question.Kind} questions."),
        };

    // Each candidate scores one plus the number of its description words in the ticket, and the scores become the
    // probabilities.
    private static ChoiceDecisionAnswer Choose(ChoiceDecisionQuestion choice, HashSet<string> words)
    {
        double[] scores = [.. choice.Candidates.Select(candidate => 1.0 + Stems(candidate.Description).Count(words.Contains))];
        double total = scores.Sum();
        int selected = Array.IndexOf(scores, scores.Max());
        return new ChoiceDecisionAnswer(
            choice.Id,
            choice.Candidates[selected].Id,
            [.. choice.Candidates.Select((candidate, index) => new DecisionProbability(candidate.Id, scores[index] / total))]);
    }

    // The level is the number of frustrated words, at most the top level, with most of the probability on it.
    private static ScoreDecisionAnswer Rate(ScoreDecisionQuestion score, HashSet<string> words)
    {
        int top = score.Levels.Count - 1;
        int level = Math.Min(top, s_frustratedWords.Count(word => words.Contains(Stem(word))) / 2);
        double[] probabilities = [.. score.Levels.Select((_, index) => index == level ? 0.8 : 0.2 / top)];
        double expected = Math.Round(probabilities.Select((probability, index) => probability * index).Sum(), 10);
        return new ScoreDecisionAnswer(
            score.Id,
            expected,
            [.. score.Levels.Select((level, index) => new DecisionProbability(level.Id, probabilities[index]))]);
    }

    // Words are compared by their first five letters, ignoring case, so "Invoice" matches "invoices".
    private static HashSet<string> Stems(string text) =>
        new(WordPattern().Matches(text).Select(match => Stem(match.Value)), StringComparer.OrdinalIgnoreCase);

    private static string Stem(string word) => word.Length > 5 ? word[..5] : word;

    [GeneratedRegex("[a-z]+", RegexOptions.IgnoreCase)]
    private static partial Regex WordPattern();
}
