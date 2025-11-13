// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

/// <summary>
/// Represents a suggestion that can be displayed and sent to the agent.
/// </summary>
public readonly struct Suggestion : IEquatable<Suggestion>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="Suggestion"/> struct.
    /// </summary>
    /// <param name="text">The display text for the suggestion.</param>
    /// <param name="message">The message to send when the suggestion is selected.</param>
    public Suggestion(string text, ChatMessage message)
    {
        Text = text;
        Message = message;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="Suggestion"/> struct with a simple text message.
    /// </summary>
    /// <param name="text">The display text for the suggestion, also used as the message content.</param>
    public Suggestion(string text)
    {
        Text = text;
        Message = new ChatMessage(ChatRole.User, text);
    }

    /// <summary>
    /// Gets the display text for the suggestion.
    /// </summary>
    public string Text { get; }

    /// <summary>
    /// Gets the message to send when the suggestion is selected.
    /// </summary>
    public ChatMessage Message { get; }

    /// <inheritdoc/>
    public override bool Equals(object? obj) => obj is Suggestion other && Equals(other);

    /// <inheritdoc/>
    public bool Equals(Suggestion other) => Text == other.Text;

    /// <inheritdoc/>
    public override int GetHashCode() => Text?.GetHashCode() ?? 0;

    /// <summary>
    /// Determines whether two <see cref="Suggestion"/> instances are equal.
    /// </summary>
    public static bool operator ==(Suggestion left, Suggestion right) => left.Equals(right);

    /// <summary>
    /// Determines whether two <see cref="Suggestion"/> instances are not equal.
    /// </summary>
    public static bool operator !=(Suggestion left, Suggestion right) => !left.Equals(right);
}

public partial class AgentSuggestions : IComponent
{
    private RenderHandle _renderHandle;
    private AgentBoundaryContext<object?>? _context;
    private IReadOnlyList<Suggestion>? _suggestions;

    [CascadingParameter] public AgentBoundaryContext<object?>? AgentContext { get; set; }

    [Parameter] public IReadOnlyList<Suggestion>? Suggestions { get; set; }

    public void Attach(RenderHandle renderHandle)
    {
        this._renderHandle = renderHandle;
    }

    public Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);
        this._context = this.AgentContext;
        this._suggestions = this.Suggestions;
        this.Render();
        return Task.CompletedTask;
    }

    private void Render()
    {
        this._renderHandle.Render(builder =>
        {
            if (this._suggestions is null || this._suggestions.Count == 0)
            {
                return;
            }

            builder.OpenElement(0, "div");
            builder.AddAttribute(1, "class", "agent-suggestions");

            for (var i = 0; i < this._suggestions.Count; i++)
            {
                var suggestion = this._suggestions[i];
                builder.OpenElement(2, "button");
                builder.SetKey(suggestion.Text);
                builder.AddAttribute(3, "class", "suggestion-button");
                builder.AddAttribute(4, "onclick", EventCallback.Factory.Create(this, () => this.SelectSuggestionAsync(suggestion)));
                builder.AddContent(5, suggestion.Text);
                builder.CloseElement();
            }

            builder.CloseElement();
        });
    }

    private async Task SelectSuggestionAsync(Suggestion suggestion)
    {
        if (this._context != null)
        {
            await this._context.SendAsync(suggestion.Message);
        }
    }
}
