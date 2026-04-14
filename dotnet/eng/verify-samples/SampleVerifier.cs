// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

namespace VerifySamples;

/// <summary>
/// Verifies sample output using deterministic checks and an AI agent
/// for non-deterministic output validation.
/// </summary>
internal sealed class SampleVerifier
{
    private readonly AIAgent? _verifierAgent;

    /// <summary>
    /// Creates a verifier. If <paramref name="chatClient"/> is provided,
    /// AI-based verification is available for non-deterministic samples.
    /// </summary>
    public SampleVerifier(ChatClient? chatClient = null)
    {
        if (chatClient is not null)
        {
            this._verifierAgent = chatClient.AsAIAgent(
                instructions: """
                    You are a test output verifier. You will be given:
                    1. The actual stdout output of a program
                    2. The stderr output (if any)
                    3. A list of expectations about what the output should contain or demonstrate

                    Your job is to determine whether the actual output satisfies each expectation.
                    Be reasonable — the output comes from an LLM so exact wording won't match, but the
                    semantic intent should be clearly satisfied.

                    In your response, you MUST:
                    - Always provide ai_reasoning with a brief overall assessment.
                    - Always provide exactly one entry in expectation_results for each expectation,
                      in the same order as the input list.
                    - For each expectation_results entry, echo the expectation text in the expectation
                      field and explain your assessment in the detail field, citing evidence from the output.
                    """,
                name: "OutputVerifier");
        }
    }

    /// <summary>
    /// Verifies the output of a sample run against its definition.
    /// </summary>
    public async Task<VerificationResult> VerifyAsync(SampleDefinition sample, SampleRunResult run)
    {
        var failures = new List<string>();

        // 1. Exit code check
        if (run.ExitCode != 0)
        {
            failures.Add($"Exit code was {run.ExitCode}, expected 0. Stderr: {Truncate(run.Stderr, 500)}");
        }

        // 2. Must-contain checks
        foreach (var expected in sample.MustContain)
        {
            if (!run.Stdout.Contains(expected, StringComparison.Ordinal))
            {
                failures.Add($"Output missing expected substring: \"{expected}\"");
            }
        }

        // 3. Must-not-contain checks
        foreach (var unexpected in sample.MustNotContain)
        {
            if (run.Stdout.Contains(unexpected, StringComparison.Ordinal))
            {
                failures.Add($"Output contains unexpected substring: \"{unexpected}\"");
            }
        }

        // 4. AI verification for non-deterministic samples
        string? aiReasoning = null;
        if (!sample.IsDeterministic && sample.ExpectedOutputDescription.Length > 0)
        {
            if (this._verifierAgent is null)
            {
                failures.Add("AI verification required but no AI agent configured (missing AZURE_OPENAI_ENDPOINT).");
            }
            else
            {
                var aiResult = await this.VerifyWithAIAsync(run.Stdout, run.Stderr, sample.ExpectedOutputDescription);
                aiReasoning = aiResult.Reasoning;

                foreach (var unmet in aiResult.UnmetExpectations)
                {
                    failures.Add($"AI expectation not met: {unmet}");
                }
            }
        }

        bool passed = failures.Count == 0;
        return new VerificationResult
        {
            SampleName = sample.Name,
            Passed = passed,
            Summary = passed ? "All checks passed" : $"{failures.Count} check(s) failed",
            Failures = failures,
            AIReasoning = aiReasoning,
        };
    }

    private async Task<(string Reasoning, List<string> UnmetExpectations)> VerifyWithAIAsync(
        string stdout,
        string stderr,
        string[] expectations)
    {
        var expectationList = string.Join("\n", expectations.Select((e, i) => $"  {i + 1}. {e}"));

        var stderrSection = string.IsNullOrWhiteSpace(stderr)
            ? ""
            : $"""

                Stderr output:
                ---
                {Truncate(stderr, 2000)}
                ---
                """;

        var prompt = $"""
            Actual program output:
            ---
            {Truncate(stdout, 4000)}
            ---
            {stderrSection}
            Expectations to verify:
            {expectationList}

            Does the output satisfy all expectations?
            """;

        try
        {
            var response = await this._verifierAgent!.RunAsync<AIVerificationResponse>(prompt);
            var result = response.Result;

            if (result is null)
            {
                return ($"AI verification returned null result. Raw: {response.Text}", ["AI verification returned null result."]);
            }

            var reasoning = string.IsNullOrWhiteSpace(result.AIReasoning)
                ? "(no reasoning provided)"
                : result.AIReasoning;

            // Collect unmet expectations as individual failures
            var unmet = new List<string>();
            if (result.ExpectationResults is { Count: > 0 })
            {
                foreach (var er in result.ExpectationResults.Where(er => !er.Met))
                {
                    var detail = string.IsNullOrWhiteSpace(er.Detail) ? er.Expectation : $"{er.Expectation} — {er.Detail}";
                    unmet.Add(detail ?? "Unknown expectation");
                }

                // If the model flagged overall failure but all individual expectations were met,
                // still treat as failure using the overall reasoning.
                if (unmet.Count == 0 && !result.Pass)
                {
                    unmet.Add(reasoning);
                }
            }
            else if (!result.Pass)
            {
                // Fallback: no per-expectation detail but overall pass is false
                unmet.Add(reasoning);
            }

            return (reasoning, unmet);
        }
        catch (Exception ex)
        {
            return ($"AI verification error: {ex.Message}", [$"AI verification error: {ex.Message}"]);
        }
    }

    private static string Truncate(string text, int maxLength)
        => text.Length <= maxLength ? text : text[..maxLength] + "... (truncated)";
}

/// <summary>
/// Structured response from the AI verification agent.
/// </summary>
[System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated by JSON deserialization via RunAsync<T>.")]
internal sealed class AIVerificationResponse
{
    /// <summary>Whether all expectations were met.</summary>
    [JsonPropertyName("pass")]
    public bool Pass { get; set; }

    /// <summary>Brief explanation of the overall assessment.</summary>
    [JsonPropertyName("ai_reasoning")]
    [Description("Always required. Brief explanation of the overall assessment, covering all expectations.")]
    public string AIReasoning { get; set; } = string.Empty;

    /// <summary>Per-expectation results.</summary>
    [JsonPropertyName("expectation_results")]
    [Description("Always required. One entry per expectation, in the same order as the input list.")]
    public List<ExpectationResult> ExpectationResults { get; set; } = [];
}

/// <summary>
/// Result for an individual expectation check.
/// </summary>
[System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated by JSON deserialization via RunAsync<T>.")]
internal sealed class ExpectationResult
{
    /// <summary>The expectation text that was evaluated.</summary>
    [JsonPropertyName("expectation")]
    [Description("Echo back the expectation text being evaluated.")]
    public string Expectation { get; set; } = string.Empty;

    /// <summary>Whether this expectation was met.</summary>
    [JsonPropertyName("met")]
    public bool Met { get; set; }

    /// <summary>Detail about how the expectation was or was not met.</summary>
    [JsonPropertyName("detail")]
    [Description("Explain how the expectation was or was not met, citing specific evidence from the output.")]
    public string Detail { get; set; } = string.Empty;
}
