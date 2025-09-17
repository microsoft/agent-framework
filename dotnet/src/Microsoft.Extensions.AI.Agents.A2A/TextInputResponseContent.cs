// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Represents text input response content.
/// </summary>
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
public sealed class TextInputResponseContent : UserInputResponseContent
#pragma warning restore MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
{
    internal TextInputResponseContent(string id, string text) : base(id)
    {
        this.Text = text;
    }

    /// <summary>
    /// A user targeted message to explain what is being requested.
    /// </summary>
    public string Text { get; set; }
}
