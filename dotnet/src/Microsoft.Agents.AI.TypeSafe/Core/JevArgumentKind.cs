// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// How the value of one tool argument is read from Jev's answers.
/// </summary>
internal enum JevArgumentKind
{
    /// <summary>The schema allows one value, so no question is asked about it.</summary>
    Const,

    /// <summary>A Choice question selects one value of an enum.</summary>
    Choice,

    /// <summary>A Noul question decides a Boolean.</summary>
    Boolean,

    /// <summary>One Noul question per enum member decides which members an array includes.</summary>
    Set,
}
