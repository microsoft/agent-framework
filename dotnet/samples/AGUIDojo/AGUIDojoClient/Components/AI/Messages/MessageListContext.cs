// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

public sealed partial class MessageListContext
{
    private bool _collectingTemplates;

    private readonly List<MessageTemplateBase> _templates = [];
    private readonly List<ContentTemplateBase> _contentTemplates = [];

    // We compute a render fragment to render each message only once and cache it here.
    private readonly Dictionary<ChatMessage, RenderFragment> _templateCache = [];

    // Track function invocations by CallId to associate calls with results.
    private readonly Dictionary<string, InvocationContext> _invocationMap = [];

    public MessageListContext(IAgentBoundaryContext context)
    {
        this.AgentBoundaryContext = context;
        Log.MessageListContextCreated(this.AgentBoundaryContext.Logger);
    }

    public IAgentBoundaryContext AgentBoundaryContext { get; }

    public void BeginCollectingTemplates()
    {
        // This is triggered by the Messages component before rendering its children.
        // In this situation we are going to render again the MessageTemplates and
        // ContentTemplates and since we can't tell if they have changed we have to
        // recompute all the templates again.
        this._collectingTemplates = true;
        this._templates.Clear();
        this._contentTemplates.Clear();
        this._templateCache.Clear();
        Log.BeganCollectingTemplates(this.AgentBoundaryContext.Logger);
    }

    public void RegisterTemplate(MessageTemplateBase template)
    {
        if (this._collectingTemplates)
        {
            this._templates.Add(template);
            Log.MessageTemplateRegistered(this.AgentBoundaryContext.Logger, this._templates.Count);
        }
    }

    public void RegisterContentTemplate(ContentTemplateBase template)
    {
        if (this._collectingTemplates)
        {
            this._contentTemplates.Add(template);
            Log.ContentTemplateRegistered(this.AgentBoundaryContext.Logger, this._contentTemplates.Count);
        }
    }

    /// <summary>
    /// Gets or creates an invocation context for the given function call.
    /// </summary>
    /// <param name="call">The function call content.</param>
    /// <returns>The invocation context for this call.</returns>
    public InvocationContext GetOrCreateInvocation(FunctionCallContent call)
    {
        if (!this._invocationMap.TryGetValue(call.CallId, out var context))
        {
            context = new InvocationContext(call);
            this._invocationMap[call.CallId] = context;
            Log.InvocationRegistered(this.AgentBoundaryContext.Logger, call.CallId, call.Name);
        }

        return context;
    }

    /// <summary>
    /// Associates a function result with its corresponding call.
    /// </summary>
    /// <param name="result">The function result content.</param>
    public void AssociateResult(FunctionResultContent result)
    {
        if (this._invocationMap.TryGetValue(result.CallId, out var context))
        {
            context.SetResult(result);
            Log.ResultAssociated(this.AgentBoundaryContext.Logger, result.CallId);
        }
    }

    /// <summary>
    /// Gets an invocation context by call ID.
    /// </summary>
    /// <param name="callId">The call ID.</param>
    /// <returns>The invocation context, or null if not found.</returns>
    public InvocationContext? GetInvocation(string callId)
    {
        return this._invocationMap.TryGetValue(callId, out var context) ? context : null;
    }

    internal RenderFragment GetTemplate(ChatMessage message)
    {
        // We are about to render the first message. If we were collecting templates, stop now.
        this._collectingTemplates = false;
        if (this._templateCache.TryGetValue(message, out var cachedTemplate))
        {
            return cachedTemplate;
        }

        var messageContext = new MessageContext(message, this);
        foreach (var template in this._templates)
        {
            if (template.When(messageContext))
            {
                var chosen = template;
                messageContext.SetTemplate(chosen);
                // We ask the template to create a RenderFragment for the message.
                // The template will render a wrapper and use the messageContext to
                // render the contents.
                // The template might call back through the messageContext to get renderers for
                // contents if the message template doesn't override the full rendering or
                // if it doesn't define the rendering for a content type.
                var renderer = chosen.ChildContent(messageContext);
                this._templateCache[message] = renderer;
                Log.TemplateResolved(this.AgentBoundaryContext.Logger, message.Role.Value);
                return renderer;
            }
        }

        throw new InvalidOperationException($"No message template found for message of type {message.Role}.");
    }

    internal RenderFragment GetContentTemplate(AIContent content)
    {
        foreach (var template in this._contentTemplates)
        {
            var contentContext = new ContentContext(content);
            if (template.When(contentContext))
            {
                return template.ChildContent(contentContext);
            }
        }

        throw new InvalidOperationException($"No content template found for content of type {content.GetType().Name}.");
    }

    private static partial class Log
    {
        [LoggerMessage(Level = LogLevel.Debug, Message = "MessageListContext created")]
        public static partial void MessageListContextCreated(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "MessageListContext began collecting templates")]
        public static partial void BeganCollectingTemplates(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Message template registered, total: {TemplateCount}")]
        public static partial void MessageTemplateRegistered(ILogger logger, int templateCount);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Content template registered, total: {TemplateCount}")]
        public static partial void ContentTemplateRegistered(ILogger logger, int templateCount);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Template resolved for message with role: {Role}")]
        public static partial void TemplateResolved(ILogger logger, string role);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Invocation registered for CallId: {CallId}, Function: {FunctionName}")]
        public static partial void InvocationRegistered(ILogger logger, string callId, string functionName);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Result associated with CallId: {CallId}")]
        public static partial void ResultAssociated(ILogger logger, string callId);
    }
}
