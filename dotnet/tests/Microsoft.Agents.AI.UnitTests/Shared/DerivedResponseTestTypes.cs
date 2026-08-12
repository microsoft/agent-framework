// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// An <see cref="AgentResponse"/> subclass carrying extra state, standing in for the derived response types an
/// inner agent may return (such as <c>AgentResponse&lt;T&gt;</c>, which carries a deserialized result).
/// </summary>
/// <remarks>
/// Used to pin that components which adjust a response on the way out — for example to report usage aggregated
/// across a loop — do so without downgrading it to a base <see cref="AgentResponse"/>.
/// </remarks>
internal sealed class TestDerivedAgentResponse(IList<ChatMessage> messages) : AgentResponse(messages)
{
    public string? DerivedState { get; set; }
}

/// <summary>
/// A <see cref="ChatResponse"/> subclass carrying extra state, standing in for the derived response types a
/// custom <see cref="IChatClient"/> may return.
/// </summary>
/// <remarks>
/// Used to pin that components which adjust a response on the way out — for example to report usage aggregated
/// across a loop — do so without downgrading it to a base <see cref="ChatResponse"/>.
/// </remarks>
internal sealed class TestDerivedChatResponse(IList<ChatMessage> messages) : ChatResponse(messages)
{
    public string? DerivedState { get; set; }
}
