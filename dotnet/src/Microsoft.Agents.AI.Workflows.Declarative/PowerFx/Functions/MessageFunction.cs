// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.PowerFx.Functions;

internal abstract class MessageFunction : ReflectionFunction
{
    protected MessageFunction(string functionName)
        : base(functionName, FormulaType.String, FormulaType.String)
    { }

    protected static FormulaValue Create(ChatRole role, StringValue input) =>
        string.IsNullOrEmpty(input.Value) ?
            FormulaValue.NewBlank(RecordType.Empty()) :
            FormulaValue.NewRecordFromFields(
                new NamedValue(TypeSchema.Discriminator, nameof(ChatMessage).ToFormula()),
                new NamedValue(TypeSchema.Message.Fields.Role, FormulaValue.New(role.Value)),
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
