// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extension methods for determining and enforcing whether a protocol descriptor represents the Agent Workflow
/// Chat Protocol.
///
/// This is defined as supporting a <see cref="List{ChatMessage}"/> and <see cref="TurnToken"/> as input. Optional support
/// for additional <see cref="ChatMessage"/> payloads (e.g. string, when a default role is defined), or other collections of
/// messages are optional to support.
/// </summary>
public static class ChatProtocolExtensions
{
    /// <summary>
    /// Determines whether the specified protocol descriptor represents the Agent Workflow Chat Protocol.
    /// </summary>
    /// <param name="descriptor">The protocol descriptor to evaluate.</param>
    /// <returns><see langword="true"/> if the protocol descriptor represents a supported chat protocol; otherwise, <see
    /// langword="false"/>.</returns>
    public static bool IsChatProtocol(this ProtocolDescriptor descriptor)
    {
        bool foundListChatMessageInput = false;
        bool foundTurnTokenInput = false;

        // We require that the workflow be a ChatProtocol; right now that is defined as accepting at
        // least List<ChatMessage> as input (pending polymorphism/interface-input support), as well as
        // TurnToken. Since output is mediated by events, which we forward, we don't need to validate
        // output type.
        foreach (Type inputType in descriptor.Accepts)
        {
            if (inputType == typeof(List<ChatMessage>))
            {
                foundListChatMessageInput = true;
            }
            else if (inputType == typeof(TurnToken))
            {
                foundTurnTokenInput = true;
            }
        }

        return foundListChatMessageInput && foundTurnTokenInput;
    }

    /// <summary>
    /// Throws an exception if the specified protocol descriptor does not represent a valid chat protocol.
    /// </summary>
    /// <param name="descriptor">The protocol descriptor to validate as a chat protocol. Cannot be null.</param>
    public static void ThrowIfNotChatProtocol(this ProtocolDescriptor descriptor)
    {
        if (!descriptor.IsChatProtocol())
        {
            throw new InvalidOperationException("Workflow does not support ChatProtocol: At least List<ChatMessage>" +
                " and TurnToken must be supported as input.");
        }
    }
}
