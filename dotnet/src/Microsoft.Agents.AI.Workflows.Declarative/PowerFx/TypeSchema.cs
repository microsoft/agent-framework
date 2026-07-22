// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.PowerFx;

internal static class TypeSchema
{
    public const string Discriminator = "__type__";

    public static class MessageContent
    {
        public static class Fields
        {
            public const string Type = nameof(Type);
            public const string Value = nameof(Value);
            public const string MediaType = nameof(MediaType);
        }

        public static class ContentTypes
        {
            public const string Text = nameof(AgentMessageContentType.Text);
            public const string ImageUrl = nameof(AgentMessageContentType.ImageUrl);
            public const string ImageFile = nameof(AgentMessageContentType.ImageFile);
        }

        public static readonly RecordType RecordType =
            RecordType.Empty()
                .Add(Fields.Type, FormulaType.String)
                .Add(Fields.Value, FormulaType.String)
                .Add(Fields.MediaType, FormulaType.String);
    }

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
            public const string Metadata = nameof(Metadata);
        }

        public static readonly RecordType RecordType =
            RecordType.Empty()
                .Add(Fields.Id, FormulaType.String)
                .Add(Fields.Role, FormulaType.String)
                .Add(Fields.Author, FormulaType.String)
                .Add(Fields.Content, MessageContent.RecordType.ToTable())
                .Add(Fields.Text, FormulaType.String)
                .Add(Fields.Metadata, RecordType.Empty());
    }
}
