﻿// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a request for user input.
/// </summary>
public sealed class InputRequest
{
    /// <summary>
    /// The prompt message to display to the user.
    /// </summary>
    public string Prompt { get; }

    internal InputRequest(string prompt)
    {
        this.Prompt = prompt;
    }
}
