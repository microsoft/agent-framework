// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.PowerFx.Functions;

internal sealed class UserMessage : ReflectionFunction
{
    public const string FunctionName = nameof(UserMessage);

    public UserMessage()
        : base(FunctionName, FormulaType.String, FormulaType.String)
    { }

    public static FormulaValue Execute(StringValue input) =>
        string.IsNullOrEmpty(input.Value) ?
            FormulaValue.NewBlank(RecordType.Empty()) :
            FormulaValue.NewRecordFromFields(
                new NamedValue(TypeSchema.Discriminator, nameof(ChatMessage).ToFormula()),
                new NamedValue(TypeSchema.Message.Fields.Role, FormulaValue.New(ChatRole.User.Value)),
                new NamedValue(
                    TypeSchema.Message.Fields.Content,
                    FormulaValue.NewTable(
                        RecordType.Empty()
                            .Add(TypeSchema.Message.Fields.ContentType, FormulaType.String)
                            .Add(TypeSchema.Message.Fields.ContentValue, FormulaType.String),
                        [
                            FormulaValue.NewRecordFromFields(
                                new NamedValue(TypeSchema.Message.Fields.ContentType, FormulaValue.New(TypeSchema.Message.ContentTypes.Text)),
                                new NamedValue(TypeSchema.Message.Fields.ContentValue, input))
                        ]
                    )
                )
        );
}
