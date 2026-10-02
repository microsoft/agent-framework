// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Turns function tools into Jev questions, so that Jev, which cannot write arguments, can still call a tool.
/// </summary>
/// <remarks>
/// <para>
/// This is a port of the tool routing in the Python TypeSafe connector (<c>_tool_calls.py</c>), with the same
/// question IDs, limits, and wording, so both connectors ask Jev the same questions. Two schema checks are stricter
/// than in Python: chains of <c>$ref</c> aliases are followed instead of excluding the tool, and <c>const</c> and
/// <c>enum</c> values must match their declared <c>type</c>, so a tool that could only fail when called is excluded.
/// </para>
/// <para>
/// A route Choice selects the tool, or <c>none</c>. Each argument must come from a closed set: a constant, an enum
/// (a Choice), a Boolean (a Noul), or an array of enum values (one Noul per value). An optional argument also gets a
/// presence Noul, so that it is passed only when the user asked for it. A tool with any other argument, such as free
/// text or a number, cannot be expressed this way; it is logged and left out, or fails the request when the tool mode
/// requires a call and no tool remains.
/// </para>
/// </remarks>
internal static class JevToolCallCompiler
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
    /// hints that keep Jev from repeating a call.
    /// </param>
    /// <param name="logger">Receives a warning for each tool that is left out.</param>
    /// <returns>The plan, or <see langword="null"/> when no tool can be called.</returns>
    public static JevToolCallPlan? Compile(
        IReadOnlyList<AIFunctionDeclaration> tools,
        ChatToolMode? toolMode,
        IReadOnlyDictionary<string, List<Dictionary<string, JsonElement>>> previousCalls,
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

        List<AIFunctionDeclaration> selected = [.. tools.Where(tool => requiredName is null || tool.Name == requiredName)];
        if (requiredName is not null && selected.Count == 0)
        {
            Throw.InvalidOperationException($"The tool mode requires the tool '{requiredName}', but the request does not have it.");
        }

        if (selected.Count > MaxRoutableTools)
        {
            Throw.InvalidOperationException(string.Format(
                CultureInfo.InvariantCulture,
                "Jev can choose among at most {0} tools per request, but the request has {1}. Offer fewer tools.",
                MaxRoutableTools,
                selected.Count));
        }

        var compiled = new List<JevCompiledTool>(selected.Count);
        var unsupported = new List<KeyValuePair<string, string>>();
        var budget = new JevQuestionBudget();
        for (int index = 0; index < selected.Count; index++)
        {
            AIFunctionDeclaration tool = selected[index];

            // Each tool reserves questions from a copy of the budget, which is committed only when the tool compiles.
            var toolBudget = new JevQuestionBudget(budget.Count);
            try
            {
                List<Dictionary<string, JsonElement>> calls = previousCalls.TryGetValue(tool.Name, out List<Dictionary<string, JsonElement>>? found) ? found : [];
                compiled.Add(CompileTool(tool, index, calls, toolBudget));
                budget.Count = toolBudget.Count;
            }
            catch (JevUnsupportedToolSchemaException ex)
            {
                unsupported.Add(new(tool.Name, ex.Message));
            }
        }

        foreach (KeyValuePair<string, string> tool in unsupported)
        {
            logger.LogToolExcluded(tool.Key, tool.Value);
        }

        if (required && compiled.Count == 0)
        {
            string details = string.Join("; ", unsupported.Select(tool => $"{tool.Key}: {tool.Value}"));
            Throw.InvalidOperationException($"The tool mode requires a tool call, but no tool can be expressed as Jev questions. {details}".TrimEnd());
        }

        if (compiled.Count == 0)
        {
            return null;
        }

        // With a single tool that must be called, there is nothing to route.
        JevCompiledTool? requiredTool = required && compiled.Count == 1 ? compiled[0] : null;
        var questions = new Dictionary<string, JevQuestion>(StringComparer.Ordinal);
        if (requiredTool is null)
        {
            var criteria = new Dictionary<string, JevEntry>(StringComparer.Ordinal);
            foreach (JevCompiledTool tool in compiled)
            {
                string name = tool.Function.Name;
                string description = string.IsNullOrWhiteSpace(tool.Function.Description)
                    ? $"Call the '{name}' tool."
                    : $"Tool '{name}': {tool.Function.Description}";
                if (previousCalls.TryGetValue(name, out List<Dictionary<string, JsonElement>>? calls) && calls.Count > 0)
                {
                    description +=
                        " Call this tool again only if the latest user request still needs a distinct execution. " +
                        $"Do not repeat argument sets already called this turn: {JevToolSchema.Describe(calls)}.";
                }

                criteria[tool.RouteLabel] = description;
            }

            if (!required)
            {
                criteria[RouteNone] = "Do not call a tool because all requested tool actions are already satisfied, or because no tool is needed.";
            }

            budget.Reserve(1);
            questions[RouteQuestionId] = new JevChoiceQuestion
            {
                Instructions = "Which available tool, if any, should handle the latest user request?",
                Criteria = criteria,
            };
        }

        foreach (JevCompiledTool tool in compiled)
        {
            foreach (KeyValuePair<string, JevQuestion> question in tool.Questions)
            {
                questions[question.Key] = question.Value;
            }
        }

        return new JevToolCallPlan
        {
            Questions = questions,
            Tools = compiled,
            RouteQuestionId = requiredTool is null ? RouteQuestionId : null,
            RequiredTool = requiredTool,
        };
    }

    private static JevCompiledTool CompileTool(AIFunctionDeclaration tool, int toolIndex, List<Dictionary<string, JsonElement>> previousCalls, JevQuestionBudget budget)
    {
        JsonElement schemaElement = tool.JsonSchema;
        Dictionary<string, JsonElement> schema = schemaElement.ValueKind switch
        {
            JsonValueKind.Object => JevToolSchema.ToMap(schemaElement),
            JsonValueKind.Undefined or JsonValueKind.Null => [],
            _ => throw new JevUnsupportedToolSchemaException("the top-level input schema must be an object"),
        };

        JevToolSchema.RejectUnsupportedKeys(schema, JevToolSchema.RootKeys, "root-level");
        if (schema.TryGetValue("type", out JsonElement type) && type.ValueKind != JsonValueKind.Null && !(type.ValueKind == JsonValueKind.String && type.ValueEquals("object")))
        {
            throw new JevUnsupportedToolSchemaException("the top-level input schema must be an object");
        }

        List<JsonProperty> properties = [];
        if (schema.TryGetValue("properties", out JsonElement propertiesElement) && propertiesElement.ValueKind != JsonValueKind.Null)
        {
            if (propertiesElement.ValueKind != JsonValueKind.Object)
            {
                throw new JevUnsupportedToolSchemaException("the input schema properties must be an object");
            }

            properties.AddRange(propertiesElement.EnumerateObject());
        }

        if (properties.Count > MaxToolProperties)
        {
            throw new JevUnsupportedToolSchemaException(string.Format(
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
                throw new JevUnsupportedToolSchemaException("the input schema required field must be a string array");
            }

            requiredNames.UnionWith(requiredElement.EnumerateArray().Select(item => item.GetString()!));
        }

        List<string> missing = [.. requiredNames.Where(name => !properties.Any(property => property.Name == name)).OrderBy(name => name, StringComparer.Ordinal)];
        if (missing.Count > 0)
        {
            throw new JevUnsupportedToolSchemaException($"required arguments are missing from properties: {string.Join(", ", missing)}");
        }

        var questions = new Dictionary<string, JevQuestion>(StringComparer.Ordinal);
        var arguments = new List<JevArgumentPlan>(properties.Count);
        for (int argumentIndex = 0; argumentIndex < properties.Count; argumentIndex++)
        {
            JsonProperty property = properties[argumentIndex];
            bool isRequired = requiredNames.Contains(property.Name);
            if (property.Value.ValueKind != JsonValueKind.Object)
            {
                throw new JevUnsupportedToolSchemaException($"argument '{property.Name}' has an invalid schema");
            }

            List<JsonElement> previousValues = [.. previousCalls.Where(call => call.ContainsKey(property.Name)).Select(call => call[property.Name])];
            try
            {
                arguments.Add(CompileArgument(tool, schema, property.Name, JevToolSchema.ToMap(property.Value), isRequired, toolIndex, argumentIndex, previousValues, budget, questions));
            }
            catch (JevUnsupportedToolSchemaException ex)
            {
                throw new JevUnsupportedToolSchemaException($"{(isRequired ? "required" : "optional")} argument '{property.Name}': {ex.Message}", ex);
            }
        }

        return new JevCompiledTool
        {
            Function = tool,
            RouteLabel = string.Create(CultureInfo.InvariantCulture, $"t{toolIndex}"),
            Questions = questions,
            Arguments = arguments,
        };
    }

    private static JevArgumentPlan CompileArgument(
        AIFunctionDeclaration tool,
        Dictionary<string, JsonElement> root,
        string name,
        Dictionary<string, JsonElement> rawSchema,
        bool required,
        int toolIndex,
        int argumentIndex,
        List<JsonElement> previousValues,
        JevQuestionBudget budget,
        Dictionary<string, JevQuestion> questions)
    {
        (Dictionary<string, JsonElement> schema, bool nullable) = JevToolSchema.Resolve(rawSchema, root);
        JevToolSchema.RejectUnsupportedKeys(schema, JevToolSchema.ArgumentKeys, "argument");

        // A required argument must be passed, and Jev cannot choose null among the closed-set values, so a required
        // nullable argument would always have to be guessed.
        if (nullable && required)
        {
            throw new JevUnsupportedToolSchemaException("required nullable arguments are not supported");
        }

        string prefix = string.Create(CultureInfo.InvariantCulture, $"{QuestionPrefix}.t{toolIndex}.a{argumentIndex}");
        string description = GetText(schema, "description") ?? GetText(rawSchema, "description") ?? GetText(schema, "title") ?? name;
        string previousInstruction = previousValues.Count > 0
            ? $" Values already used for this argument in earlier calls this turn: {JevToolSchema.Describe(previousValues)}. Choose a different value when the user requested another distinct call."
            : string.Empty;
        string? presenceQuestionId = required ? null : prefix + ".present";

        void AddPresenceQuestion()
        {
            if (presenceQuestionId is not null)
            {
                questions[presenceQuestionId] = new JevNoulQuestion
                {
                    Instructions = $"For the {tool.Name} tool, did the user explicitly specify the {name} argument? Argument meaning: {description}.{previousInstruction}",
                };
            }
        }

        if (schema.TryGetValue("const", out JsonElement constValue))
        {
            JevToolSchema.EnsureValuesMatchType(schema, [constValue], "argument", "const value", "type");
            budget.Reserve(required ? 0 : 1);
            AddPresenceQuestion();
            return new JevArgumentPlan { Name = name, Kind = JevArgumentKind.Const, PresenceQuestionId = presenceQuestionId, ConstValue = constValue };
        }

        if (schema.TryGetValue("enum", out JsonElement enumElement) && enumElement.ValueKind == JsonValueKind.Array && enumElement.GetArrayLength() > 0)
        {
            List<JsonElement> values = [.. enumElement.EnumerateArray()];
            if (values.Count > MaxEnumValues)
            {
                throw new JevUnsupportedToolSchemaException(string.Format(CultureInfo.InvariantCulture, "enum defines {0} values; the supported maximum is {1}", values.Count, MaxEnumValues));
            }

            JevToolSchema.EnsureValuesMatchType(schema, values, "argument", "enum value", "type");
            if (values.Count == 1)
            {
                budget.Reserve(required ? 0 : 1);
                AddPresenceQuestion();
                return new JevArgumentPlan { Name = name, Kind = JevArgumentKind.Const, PresenceQuestionId = presenceQuestionId, ConstValue = values[0] };
            }

            var labeled = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
            var criteria = new Dictionary<string, JevEntry>(StringComparer.Ordinal);
            for (int index = 0; index < values.Count; index++)
            {
                string label = string.Create(CultureInfo.InvariantCulture, $"v{index}");
                labeled[label] = values[index];
                criteria[label] = JevToolSchema.Describe(values[index]);
            }

            string questionId = prefix + ".value";
            budget.Reserve(required ? 1 : 2);
            AddPresenceQuestion();
            questions[questionId] = new JevChoiceQuestion
            {
                Instructions = $"For the {tool.Name} tool, choose the {name} argument. Argument meaning: {description}.{previousInstruction}",
                Criteria = criteria,
            };
            return new JevArgumentPlan { Name = name, Kind = JevArgumentKind.Choice, PresenceQuestionId = presenceQuestionId, ValueQuestionId = questionId, Values = labeled };
        }

        string? schemaType = schema.TryGetValue("type", out JsonElement typeElement) && typeElement.ValueKind == JsonValueKind.String ? typeElement.GetString() : null;
        if (schemaType == "boolean")
        {
            string questionId = prefix + ".value";
            budget.Reserve(required ? 1 : 2);
            AddPresenceQuestion();
            questions[questionId] = new JevNoulQuestion
            {
                Instructions = $"For the {tool.Name} tool, should the {name} argument be true? Argument meaning: {description}.{previousInstruction}",
            };
            return new JevArgumentPlan { Name = name, Kind = JevArgumentKind.Boolean, PresenceQuestionId = presenceQuestionId, ValueQuestionId = questionId };
        }

        if (schemaType == "array")
        {
            if (!schema.TryGetValue("items", out JsonElement itemsElement) || itemsElement.ValueKind != JsonValueKind.Object)
            {
                throw new JevUnsupportedToolSchemaException("array items must define an enum");
            }

            (Dictionary<string, JsonElement> items, bool itemsNullable) = JevToolSchema.Resolve(JevToolSchema.ToMap(itemsElement), root);
            JevToolSchema.RejectUnsupportedKeys(items, JevToolSchema.ArrayItemKeys, "array item");
            if (itemsNullable)
            {
                throw new JevUnsupportedToolSchemaException("nullable array members are not supported");
            }

            if (!items.TryGetValue("enum", out JsonElement membersElement) || membersElement.ValueKind != JsonValueKind.Array || membersElement.GetArrayLength() == 0)
            {
                throw new JevUnsupportedToolSchemaException("array items must define a non-empty enum");
            }

            List<JsonElement> members = [.. membersElement.EnumerateArray()];
            if (members.Count > MaxEnumValues)
            {
                throw new JevUnsupportedToolSchemaException(string.Format(CultureInfo.InvariantCulture, "array enum defines {0} values; the supported maximum is {1}", members.Count, MaxEnumValues));
            }

            JevToolSchema.EnsureValuesMatchType(items, members, "array item", "array enum member", "item type");

            budget.Reserve(members.Count + (required ? 0 : 1));
            AddPresenceQuestion();
            var memberQuestions = new List<KeyValuePair<string, JsonElement>>(members.Count);
            for (int index = 0; index < members.Count; index++)
            {
                string questionId = string.Create(CultureInfo.InvariantCulture, $"{prefix}.m{index}");
                questions[questionId] = new JevNoulQuestion
                {
                    Instructions = $"For the {tool.Name} tool, should the {name} argument include {JevToolSchema.Describe(members[index])}? Argument meaning: {description}.{previousInstruction}",
                };
                memberQuestions.Add(new(questionId, members[index]));
            }

            return new JevArgumentPlan { Name = name, Kind = JevArgumentKind.Set, PresenceQuestionId = presenceQuestionId, Members = memberQuestions };
        }

        throw new JevUnsupportedToolSchemaException("only const, enum, boolean, and arrays of enum values are supported");
    }

    private static string? GetText(Dictionary<string, JsonElement> schema, string key) =>
        schema.TryGetValue(key, out JsonElement value) && value.ValueKind == JsonValueKind.String && value.GetString() is { Length: > 0 } text ? text : null;
}
