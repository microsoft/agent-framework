// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.MEAI;

/// <summary>
/// Marks an existing <see cref="AIFunction"/> with additional metadata to indicate that it is not invocable.
/// </summary>
internal class NonInvocableAIFunction(AIFunction innerFunction) : DelegatingAIFunction(innerFunction);
