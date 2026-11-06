// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// The tool call that Jev selected: the function and the arguments decoded from its answers.
/// </summary>
internal readonly record struct JevToolCall(AIFunctionDeclaration Function, Dictionary<string, object?> Arguments);
