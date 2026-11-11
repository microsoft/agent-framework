// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// How the value of one tool argument is read from the answers of a decision model.
/// </summary>
internal enum DecisionArgumentKind
{
    /// <summary>The schema allows one value, so no question is asked about it.</summary>
    Const,

    /// <summary>A Choice question selects one value of an enum.</summary>
    Choice,

    /// <summary>A Binary question decides a Boolean.</summary>
    Boolean,

    /// <summary>One Binary question per enum member decides which members an array includes.</summary>
    Set,
}
