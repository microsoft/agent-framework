// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Represents text input request content.
/// </summary>
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
public sealed class TextInputRequestContent : UserInputRequestContent
#pragma warning restore MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
{
    internal TextInputRequestContent(string text) : base(Guid.NewGuid().ToString())
    {
        this.Text = text ?? throw new ArgumentNullException(nameof(text));
    }

    /// <summary>
    /// A message explaining what is being requested.
    /// </summary>
    public string Text { get; set; }

    /// <summary>
    /// Creates a <see cref="TextInputResponseContent"/> response associated with this request.
    /// </summary>
    /// <param name="text">The text of the response.</param>
    /// <returns>The created <see cref="TextInputResponseContent"/>.</returns>
    public TextInputResponseContent CreateResponse(string text)
    {
        return new TextInputResponseContent(this.Id, text);
    }
}
