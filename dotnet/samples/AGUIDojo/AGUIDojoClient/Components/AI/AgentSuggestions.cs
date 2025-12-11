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
        this.Text = text;
        this.Message = message;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="Suggestion"/> struct with a simple text message.
    /// </summary>
    /// <param name="text">The display text for the suggestion, also used as the message content.</param>
    public Suggestion(string text)
    {
        this.Text = text;
        this.Message = new ChatMessage(ChatRole.User, text);
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
    public override bool Equals(object? obj) => obj is Suggestion other && this.Equals(other);

    /// <inheritdoc/>
    public bool Equals(Suggestion other) => this.Text == other.Text;

    /// <inheritdoc/>
    public override int GetHashCode() => this.Text?.GetHashCode() ?? 0;

    /// <summary>
    /// Determines whether two <see cref="Suggestion"/> instances are equal.
    /// </summary>
    public static bool operator ==(Suggestion left, Suggestion right) => left.Equals(right);

    /// <summary>
    /// Determines whether two <see cref="Suggestion"/> instances are not equal.
    /// </summary>
    public static bool operator !=(Suggestion left, Suggestion right) => !left.Equals(right);
}

public sealed partial class AgentSuggestions : IComponent, IDisposable
{
    private RenderHandle _renderHandle;
    private AgentBoundaryContext<object?>? _context;
    private IReadOnlyList<Suggestion>? _suggestions;
    private RunStatusSubscription? _subscription;

    [CascadingParameter] public AgentBoundaryContext<object?>? AgentContext { get; set; }

    [Parameter] public IReadOnlyList<Suggestion>? Suggestions { get; set; }

    public void Attach(RenderHandle renderHandle)
    {
        this._renderHandle = renderHandle;
    }

    public Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);

        // Unsubscribe from previous context if it changed
        if (this._context != this.AgentContext)
        {
            this._subscription?.Dispose();
            this._context = this.AgentContext;

            // Subscribe to run status changes
            if (this._context != null)
            {
                this._subscription = this._context.SubscribeToRunStatusChanges(this.OnRunStatusChanged);
            }
        }

        this._suggestions = this.Suggestions;
        this.Render();
        return Task.CompletedTask;
    }

    private void OnRunStatusChanged()
    {
        this.Render();
    }

    private void Render()
    {
        var isProcessing = this._context?.IsProcessing ?? false;

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
                builder.AddAttribute(5, "disabled", isProcessing);
                builder.AddContent(6, suggestion.Text);
                builder.CloseElement();
            }

            builder.CloseElement();
        });
    }

    private async Task SelectSuggestionAsync(Suggestion suggestion)
    {
        if (this._context is { IsProcessing: false })
        {
            await this._context.SendAsync(suggestion.Message);
        }
    }

    public void Dispose()
    {
        this._subscription?.Dispose();
    }
}
