// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Counts the internal questions that tool routing adds to a request, and stops the request when they exceed
/// <see cref="MaxInternalQuestions"/>.
/// </summary>
/// <remarks>
/// Each tool is compiled against a copy of the budget, which is committed only when the tool compiles. A tool that
/// is excluded for an unsupported schema therefore returns the questions it reserved to the tools after it.
/// </remarks>
internal sealed class JevQuestionBudget
{
    public const int MaxInternalQuestions = 128;

    public JevQuestionBudget(int count = 0)
    {
        this.Count = count;
    }

    public int Count { get; set; }

    public void Reserve(int count)
    {
        int next = this.Count + count;
        if (next > MaxInternalQuestions)
        {
            // Too many questions is a property of the whole tool set, not of one tool, so it stops the request instead
            // of excluding the tool that crossed the limit.
            Throw.InvalidOperationException(string.Format(
                CultureInfo.InvariantCulture,
                "The tools need more than {0} internal Jev questions. Offer fewer tools, or tools with fewer arguments.",
                MaxInternalQuestions));
        }

        this.Count = next;
    }
}
