// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// The tool call that a decision model selected: the function and the arguments decoded from its answers.
/// </summary>
internal readonly record struct DecisionToolCall(AIFunctionDeclaration Function, Dictionary<string, object?> Arguments);
