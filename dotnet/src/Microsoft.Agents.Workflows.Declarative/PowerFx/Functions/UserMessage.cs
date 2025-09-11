// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx.Functions;

internal sealed class UserMessage : ReflectionFunction
{
    public static class Fields // %%% MOVE (not specific to this function)
    {
        public const string Id = nameof(Id);
        public const string ConversationId = nameof(ConversationId);
        public const string AgentId = nameof(AgentId);
        public const string RunId = nameof(RunId);
        public const string Role = nameof(Role);
        public const string Author = nameof(Author);
        public const string Content = nameof(Content);
        public const string ContentType = nameof(ContentType);
        public const string ContentValue = nameof(ContentValue);
        public const string Metadata = nameof(Metadata);
        //public const string Role = "role"; // %%% TEST && REMOVE
        //public const string Content = "content";
        //public const string ContentType = "type";
        //public const string ContentValue = "value";
    }

    public static class ContentTypes
    {
        public const string Text = nameof(AgentMessageContentType.Text);
        public const string ImageUrl = nameof(AgentMessageContentType.ImageUrl);
        public const string ImageFile = nameof(AgentMessageContentType.ImageFile);
    }

    public const string FunctionName = nameof(UserMessage);

    public UserMessage()
        : base(FunctionName, FormulaType.String, FormulaType.String)
    { }

    public static FormulaValue Execute(StringValue input) =>
        string.IsNullOrEmpty(input.Value) ?
            FormulaValue.NewBlank(RecordType.Empty()) :
            FormulaValue.NewRecordFromFields(
                new NamedValue(Fields.Role, FormulaValue.New(ChatRole.User.Value)),
                new NamedValue(
                    Fields.Content,
                    FormulaValue.NewTable(
                        RecordType.Empty()
                            .Add(Fields.ContentType, FormulaType.String)
                            .Add(Fields.ContentValue, FormulaType.String),
                        [
                            FormulaValue.NewRecordFromFields(
                                new NamedValue(Fields.ContentType, FormulaValue.New(ContentTypes.Text)),
                                new NamedValue(Fields.ContentValue, input))
                        ]
                    )
                )
        );
}
