// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// Turns function tools into decision questions, so that a decision model, which cannot write arguments, can still call
/// a tool.
/// </summary>
/// <remarks>
/// <para>
/// This is a port of the tool routing in the Python TypeSafe connector (<c>_tool_calls.py</c>), with the same
/// question IDs, limits, and wording, so both connectors ask the same questions. Two schema checks are stricter
/// than in Python: chains of <c>$ref</c> aliases are followed instead of excluding the tool, and <c>const</c> and
/// <c>enum</c> values must satisfy their declared constraints, so a tool that could fail when called is excluded.
/// </para>
/// <para>
/// A route Choice selects the tool, or <c>none</c>. Each argument must come from a closed set: a constant, an enum
/// (a Choice), a Boolean (a Binary question), or an array of enum values (one Binary question per value). An optional
/// argument also gets a presence Binary question, so that it is passed only when the user asked for it. A tool with any
/// other argument, such as free text or a number, cannot be expressed this way; it is logged and left out, or fails the
/// request when the tool mode requires a call and no tool remains.
/// </para>
/// </remarks>
internal static class DecisionToolCallCompiler
{
    public const string QuestionPrefix = "__af_tool__";
    public const string RouteQuestionId = QuestionPrefix + ".route";
    public const string RouteNone = "none";
    public const int MaxRoutableTools = 32;
    public const int MaxToolProperties = 64;
    public const int MaxEnumValues = 64;

    /// <summary>
    /// Rejects caller question IDs that could collide with the internal tool questions.
    /// </summary>
    public static void EnsureNoReservedQuestionIds(IEnumerable<string> questionIds)
    {
        List<string> reserved = [.. questionIds.Where(id => id.StartsWith(QuestionPrefix, StringComparison.Ordinal)).OrderBy(id => id, StringComparer.Ordinal)];
        if (reserved.Count > 0)
        {
            Throw.ArgumentException("questions", $"Question IDs that start with '{QuestionPrefix}' are reserved for tool calls: {string.Join(", ", reserved)}.");
        }
    }

    /// <summary>
    /// Compiles the tools that the tool mode allows into a tool call plan.
    /// </summary>
    /// <param name="tools">The function tools of the request.</param>
    /// <param name="toolMode">The tool mode of the request; <see langword="null"/> means <see cref="ChatToolMode.Auto"/>.</param>
    /// <param name="previousCalls">
    /// The argument sets of the tools already called in the current turn, by tool name, oldest first. They become
    /// hints that keep the model from repeating a call.
    /// </param>
    /// <param name="modelName">The name of the decision model, such as <c>Jev</c>, for messages.</param>
    /// <param name="logger">Receives a warning for each tool that is left out.</param>
    /// <returns>The plan, or <see langword="null"/> when no tool can be called.</returns>
    public static DecisionToolCallPlan? Compile(
        IReadOnlyList<AIFunctionDeclaration> tools,
        ChatToolMode? toolMode,
        IReadOnlyDictionary<string, List<Dictionary<string, JsonElement>>> previousCalls,
        string modelName,
        ILogger logger)
    {
        if (toolMode is NoneChatToolMode)
        {
            return null;
        }

        bool required = toolMode is RequiredChatToolMode;
        string? requiredName = (toolMode as RequiredChatToolMode)?.RequiredFunctionName;
        if (tools.Count == 0)
        {
            if (required)
            {
                Throw.InvalidOperationException("The tool mode requires a tool call, but the request has no tools.");
            }

            return null;
        }

        List<AIFunctionDeclaration> selected = [.. tools.Where(tool => requiredName is null || string.Equals(tool.Name, requiredName, StringComparison.Ordinal))];
        if (requiredName is not null && selected.Count == 0)
        {
            Throw.InvalidOperationException($"The tool mode requires the tool '{requiredName}', but the request does not have it.");
        }

        if (selected.Count > MaxRoutableTools)
        {
            Throw.InvalidOperationException(string.Format(
                CultureInfo.InvariantCulture,
                "{0} can choose among at most {1} tools per request, but the request has {2}. Offer fewer tools.",
                modelName,
                MaxRoutableTools,
                selected.Count));
        }

        var compiled = new List<DecisionCompiledTool>(selected.Count);
        var unsupported = new List<KeyValuePair<string, string>>();
        var budget = new DecisionQuestionBudget();
        for (int index = 0; index < selected.Count; index++)
        {
            AIFunctionDeclaration tool = selected[index];

            // Each tool reserves questions from a copy of the budget, which is committed only when the tool compiles.
            var toolBudget = new DecisionQuestionBudget(budget.Count);
            try
            {
                List<Dictionary<string, JsonElement>> calls = previousCalls.TryGetValue(tool.Name, out List<Dictionary<string, JsonElement>>? found) ? found : [];
                compiled.Add(CompileTool(tool, index, calls, toolBudget));
                budget.Count = toolBudget.Count;
            }
            catch (DecisionUnsupportedToolSchemaException ex)
            {
                unsupported.Add(new(tool.Name, ex.Message));
            }
        }

        foreach (KeyValuePair<string, string> tool in unsupported)
        {
            logger.LogToolExcluded(modelName, tool.Key, tool.Value);
        }

        if (required && compiled.Count == 0)
        {
            string details = string.Join("; ", unsupported.Select(tool => $"{tool.Key}: {tool.Value}"));
            Throw.InvalidOperationException($"The tool mode requires a tool call, but no tool can be expressed as {modelName} questions. {details}".TrimEnd());
        }

        if (compiled.Count == 0)
        {
            return null;
        }

        // With a single tool that must be called, there is nothing to route.
        DecisionCompiledTool? requiredTool = required && compiled.Count == 1 ? compiled[0] : null;
        var questions = new Dictionary<string, DecisionQuestion>(StringComparer.Ordinal);
        if (requiredTool is null)
        {
            var candidates = new List<DecisionCandidate>(compiled.Count + 1);
            foreach (DecisionCompiledTool tool in compiled)
            {
                string name = tool.Function.Name;
                string description = string.IsNullOrWhiteSpace(tool.Function.Description)
                    ? $"Call the '{name}' tool."
                    : $"Tool '{name}': {tool.Function.Description}";
                if (previousCalls.TryGetValue(name, out List<Dictionary<string, JsonElement>>? calls) && calls.Count > 0)
                {
                    description +=
                        " Call this tool again only if the latest user request still needs a distinct execution. " +
                        $"Do not repeat argument sets already called this turn: {DecisionToolSchema.Describe(calls)}.";
                }

                candidates.Add(new DecisionCandidate(tool.RouteLabel, description));
            }

            if (!required)
            {
                candidates.Add(new DecisionCandidate(RouteNone, "Do not call a tool because all requested tool actions are already satisfied, or because no tool is needed."));
            }

            _ = budget.TryReserve(1);
            budget.Validate();
            questions[RouteQuestionId] = new ChoiceDecisionQuestion(
                RouteQuestionId,
                "Which available tool, if any, should handle the latest user request?",
                candidates);
        }

        foreach (DecisionCompiledTool tool in compiled)
        {
            foreach (KeyValuePair<string, DecisionQuestion> question in tool.Questions)
            {
                questions[question.Key] = question.Value;
            }
        }

        return new DecisionToolCallPlan
        {
            Questions = questions,
            Tools = compiled,
            RouteQuestionId = requiredTool is null ? RouteQuestionId : null,
            RequiredTool = requiredTool,
        };
    }

    private static DecisionCompiledTool CompileTool(AIFunctionDeclaration tool, int toolIndex, List<Dictionary<string, JsonElement>> previousCalls, DecisionQuestionBudget budget)
    {
        JsonElement schemaElement = tool.JsonSchema;
        Dictionary<string, JsonElement> schema = schemaElement.ValueKind switch
        {
            JsonValueKind.Object => DecisionToolSchema.ToMap(schemaElement),
            JsonValueKind.Undefined or JsonValueKind.Null => [],
            _ => throw new DecisionUnsupportedToolSchemaException("the top-level input schema must be an object"),
        };

        DecisionToolSchema.RejectUnsupportedKeys(schema, DecisionToolSchema.RootKeys, "root-level");
        if (schema.TryGetValue("type", out JsonElement type) && type.ValueKind != JsonValueKind.Null && !(type.ValueKind == JsonValueKind.String && type.ValueEquals("object")))
        {
            throw new DecisionUnsupportedToolSchemaException("the top-level input schema must be an object");
        }

        List<JsonProperty> properties = [];
        if (schema.TryGetValue("properties", out JsonElement propertiesElement) && propertiesElement.ValueKind != JsonValueKind.Null)
        {
            if (propertiesElement.ValueKind != JsonValueKind.Object)
            {
                throw new DecisionUnsupportedToolSchemaException("the input schema properties must be an object");
            }

            properties.AddRange(propertiesElement.EnumerateObject());
        }

        if (properties.Count > MaxToolProperties)
        {
            throw new DecisionUnsupportedToolSchemaException(string.Format(
                CultureInfo.InvariantCulture,
                "the input schema defines {0} properties; the supported maximum is {1}",
                properties.Count,
                MaxToolProperties));
        }

        var requiredNames = new HashSet<string>(StringComparer.Ordinal);
        if (schema.TryGetValue("required", out JsonElement requiredElement))
        {
            if (requiredElement.ValueKind != JsonValueKind.Array || requiredElement.EnumerateArray().Any(item => item.ValueKind != JsonValueKind.String))
            {
                throw new DecisionUnsupportedToolSchemaException("the input schema required field must be a string array");
            }

            requiredNames.UnionWith(requiredElement.EnumerateArray().Select(item => item.GetString()!));
        }

        List<string> missing = [.. requiredNames.Where(name => !properties.Any(property => property.Name == name)).OrderBy(name => name, StringComparer.Ordinal)];
        if (missing.Count > 0)
        {
            throw new DecisionUnsupportedToolSchemaException($"required arguments are missing from properties: {string.Join(", ", missing)}");
        }

        var questions = new Dictionary<string, DecisionQuestion>(StringComparer.Ordinal);
        var arguments = new List<DecisionArgumentPlan>(properties.Count);
        for (int argumentIndex = 0; argumentIndex < properties.Count; argumentIndex++)
        {
            JsonProperty property = properties[argumentIndex];
            bool isRequired = requiredNames.Contains(property.Name);
            if (property.Value.ValueKind != JsonValueKind.Object)
            {
                throw new DecisionUnsupportedToolSchemaException($"argument '{property.Name}' has an invalid schema");
            }

            List<JsonElement> previousValues = [.. previousCalls.Where(call => call.ContainsKey(property.Name)).Select(call => call[property.Name])];
            try
            {
                if (CompileArgument(tool, schema, property.Name, DecisionToolSchema.ToMap(property.Value), isRequired, toolIndex, argumentIndex, previousValues, budget, questions) is { } argument)
                {
                    arguments.Add(argument);
                }
            }
            catch (DecisionUnsupportedToolSchemaException ex)
            {
                throw new DecisionUnsupportedToolSchemaException($"{(isRequired ? "required" : "optional")} argument '{property.Name}': {ex.Message}", ex);
            }
        }

        // Unsupported tools are excluded even if their earlier arguments exceeded the question budget.
        budget.Validate();
        return new DecisionCompiledTool
        {
            Function = tool,
            RouteLabel = string.Create(CultureInfo.InvariantCulture, $"t{toolIndex}"),
            Questions = questions,
            Arguments = arguments,
        };
    }

    private static DecisionArgumentPlan? CompileArgument(
        AIFunctionDeclaration tool,
        Dictionary<string, JsonElement> root,
        string name,
        Dictionary<string, JsonElement> rawSchema,
        bool required,
        int toolIndex,
        int argumentIndex,
        List<JsonElement> previousValues,
        DecisionQuestionBudget budget,
        Dictionary<string, DecisionQuestion> questions)
    {
        (Dictionary<string, JsonElement> schema, bool nullable) = DecisionToolSchema.Resolve(rawSchema, root);
        DecisionToolSchema.RejectUnsupportedKeys(schema, DecisionToolSchema.ArgumentKeys, "argument");

        // A required argument must be passed, and the model cannot choose null among the closed-set values, so a
        // required nullable argument would always have to be guessed.
        if (nullable && required)
        {
            throw new DecisionUnsupportedToolSchemaException("required nullable arguments are not supported");
        }

        string prefix = string.Create(CultureInfo.InvariantCulture, $"{QuestionPrefix}.t{toolIndex}.a{argumentIndex}");
        string description = GetText(schema, "description") ?? GetText(rawSchema, "description") ?? GetText(schema, "title") ?? name;
        string previousInstruction = previousValues.Count > 0
            ? $" Values already used for this argument in earlier calls this turn: {DecisionToolSchema.Describe(previousValues)}. Choose a different value when the user requested another distinct call."
            : string.Empty;
        string? presenceQuestionId = required ? null : prefix + ".present";

        void AddPresenceQuestion()
        {
            if (presenceQuestionId is not null)
            {
                questions[presenceQuestionId] = new BinaryDecisionQuestion(
                    presenceQuestionId,
                    $"For the {tool.Name} tool, did the user explicitly specify the {name} argument? Argument meaning: {description}.{previousInstruction}");
            }
        }

        if (schema.TryGetValue("const", out JsonElement constValue))
        {
            DecisionToolSchema.EnsureValuesMatchSchema(schema, [constValue], root, "const value");
            if (!budget.TryReserve(required ? 0 : 1))
            {
                return null;
            }

            AddPresenceQuestion();
            return new DecisionArgumentPlan { Name = name, Kind = DecisionArgumentKind.Const, PresenceQuestionId = presenceQuestionId, ConstValue = constValue };
        }

        if (schema.TryGetValue("enum", out JsonElement enumElement))
        {
            List<JsonElement> values = DecisionToolSchema.ReadEnumValues(enumElement, "enum");
            DecisionToolSchema.EnsureValuesMatchSchema(schema, values, root, "enum value");
            if (values.Count == 1)
            {
                if (!budget.TryReserve(required ? 0 : 1))
                {
                    return null;
                }

                AddPresenceQuestion();
                return new DecisionArgumentPlan { Name = name, Kind = DecisionArgumentKind.Const, PresenceQuestionId = presenceQuestionId, ConstValue = values[0] };
            }

            if (!budget.TryReserve(required ? 1 : 2))
            {
                return null;
            }

            var labeled = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
            var candidates = new List<DecisionCandidate>(values.Count);
            for (int index = 0; index < values.Count; index++)
            {
                string label = string.Create(CultureInfo.InvariantCulture, $"v{index}");
                labeled[label] = values[index];
                candidates.Add(new DecisionCandidate(label, DecisionToolSchema.Describe(values[index])));
            }

            string questionId = prefix + ".value";
            AddPresenceQuestion();
            questions[questionId] = new ChoiceDecisionQuestion(
                questionId,
                $"For the {tool.Name} tool, choose the {name} argument. Argument meaning: {description}.{previousInstruction}",
                candidates);
            return new DecisionArgumentPlan { Name = name, Kind = DecisionArgumentKind.Choice, PresenceQuestionId = presenceQuestionId, ValueQuestionId = questionId, Values = labeled };
        }

        string? schemaType = schema.TryGetValue("type", out JsonElement typeElement) && typeElement.ValueKind == JsonValueKind.String ? typeElement.GetString() : null;
        if (string.Equals(schemaType, "boolean", StringComparison.Ordinal))
        {
            string questionId = prefix + ".value";
            if (!budget.TryReserve(required ? 1 : 2))
            {
                return null;
            }

            AddPresenceQuestion();
            questions[questionId] = new BinaryDecisionQuestion(
                questionId,
                $"For the {tool.Name} tool, should the {name} argument be true? Argument meaning: {description}.{previousInstruction}");
            return new DecisionArgumentPlan { Name = name, Kind = DecisionArgumentKind.Boolean, PresenceQuestionId = presenceQuestionId, ValueQuestionId = questionId };
        }

        if (string.Equals(schemaType, "array", StringComparison.Ordinal))
        {
            Dictionary<string, JsonElement> items = DecisionToolSchema.ResolveArrayItems(schema, root);
            if (!items.TryGetValue("enum", out JsonElement membersElement) || membersElement.ValueKind != JsonValueKind.Array || membersElement.GetArrayLength() == 0)
            {
                throw new DecisionUnsupportedToolSchemaException("array items must define a non-empty enum");
            }

            List<JsonElement> members = DecisionToolSchema.ReadEnumValues(membersElement, "array enum");
            DecisionToolSchema.EnsureValuesMatchType(items, members, "array item", "array enum member", "item type");

            if (!budget.TryReserve(members.Count + (required ? 0 : 1)))
            {
                return null;
            }

            AddPresenceQuestion();
            var memberQuestions = new List<KeyValuePair<string, JsonElement>>(members.Count);
            for (int index = 0; index < members.Count; index++)
            {
                string questionId = string.Create(CultureInfo.InvariantCulture, $"{prefix}.m{index}");
                questions[questionId] = new BinaryDecisionQuestion(
                    questionId,
                    $"For the {tool.Name} tool, should the {name} argument include {DecisionToolSchema.Describe(members[index])}? Argument meaning: {description}.{previousInstruction}");
                memberQuestions.Add(new(questionId, members[index]));
            }

            return new DecisionArgumentPlan { Name = name, Kind = DecisionArgumentKind.Set, PresenceQuestionId = presenceQuestionId, Members = memberQuestions };
        }

        throw new DecisionUnsupportedToolSchemaException("only const, enum, boolean, and arrays of enum values are supported");
    }

    private static string? GetText(Dictionary<string, JsonElement> schema, string key) =>
        schema.TryGetValue(key, out JsonElement value) && value.ValueKind == JsonValueKind.String && value.GetString() is { Length: > 0 } text ? text : null;
}
