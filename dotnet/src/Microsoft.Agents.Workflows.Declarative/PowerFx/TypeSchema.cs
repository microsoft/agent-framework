// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx.Functions;

internal static class TypeSchema
{
    public static class Message
    {
        public static class Fields
        {
            public const string Id = nameof(Id);
            public const string ConversationId = nameof(ConversationId);
            public const string AgentId = nameof(AgentId);
            public const string RunId = nameof(RunId);
            public const string Role = nameof(Role);
            public const string Author = nameof(Author);
            public const string Text = nameof(Text);
            public const string Content = nameof(Content);
            public const string ContentType = nameof(ContentType);
            public const string ContentValue = nameof(ContentValue);
            public const string Metadata = nameof(Metadata);
        }

        public static class ContentTypes
        {
            public const string Text = nameof(AgentMessageContentType.Text);
            public const string ImageUrl = nameof(AgentMessageContentType.ImageUrl);
            public const string ImageFile = nameof(AgentMessageContentType.ImageFile);
        }
    }
}
