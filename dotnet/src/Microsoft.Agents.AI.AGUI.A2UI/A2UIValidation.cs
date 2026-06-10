// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.AGUI.A2UI;

/// <summary>
/// Error codes emitted by <see cref="A2UIComponentValidator"/>.
/// </summary>
/// <remarks>
/// The string values are part of the cross-language A2UI contract (shared with the
/// TypeScript and Python toolkits) and feed back into subagent retry prompts; they
/// must not diverge from the sibling implementations.
/// </remarks>
public static class A2UIValidationErrorCodes
{
    /// <summary>The component set is missing or empty.</summary>
    public const string EmptyComponents = "empty_components";

    /// <summary>A component has no usable string <c>id</c>.</summary>
    public const string MissingId = "missing_id";

    /// <summary>A component has no usable string <c>component</c> type.</summary>
    public const string MissingComponentType = "missing_component_type";

    /// <summary>Two or more components share the same <c>id</c>.</summary>
    public const string DuplicateId = "duplicate_id";

    /// <summary>No component carries the mandatory <c>id</c> of <c>"root"</c>.</summary>
    public const string NoRoot = "no_root";

    /// <summary>A component type is not present in the supplied catalog.</summary>
    public const string UnknownComponent = "unknown_component";

    /// <summary>A component lacks a property the catalog marks as required.</summary>
    public const string MissingRequiredProp = "missing_required_prop";

    /// <summary>A child reference points at a component id that does not exist.</summary>
    public const string UnresolvedChild = "unresolved_child";

    /// <summary>An absolute data binding path does not resolve in the data model.</summary>
    public const string UnresolvedBinding = "unresolved_binding";
}

/// <summary>
/// A single semantic validation finding for an A2UI component tree.
/// </summary>
/// <param name="Code">One of the <see cref="A2UIValidationErrorCodes"/> values.</param>
/// <param name="Path">A JSON-pointer-style location, e.g. <c>components[1].rating</c>.</param>
/// <param name="Message">A human/model-readable description used in retry prompts.</param>
public sealed record A2UIValidationError(string Code, string Path, string Message);

/// <summary>
/// The outcome of validating an A2UI component tree.
/// </summary>
/// <param name="Valid"><see langword="true"/> when no errors were found.</param>
/// <param name="Errors">The findings, empty when <paramref name="Valid"/> is <see langword="true"/>.</param>
public sealed record A2UIValidationResult(bool Valid, IReadOnlyList<A2UIValidationError> Errors);

/// <summary>
/// An inline component catalog used for semantic validation: component schemas
/// (standard JSON Schema fragments with an optional <c>required</c> array) keyed by component name.
/// </summary>
public sealed class A2UIValidationCatalog
{
    /// <summary>
    /// Initializes a new instance of the <see cref="A2UIValidationCatalog"/> class.
    /// </summary>
    /// <param name="components">Component schemas keyed by component name.</param>
    public A2UIValidationCatalog(JsonObject components)
    {
        this.Components = components ?? throw new ArgumentNullException(nameof(components));
    }

    /// <summary>
    /// Gets the component schemas keyed by component name.
    /// </summary>
    public JsonObject Components { get; }
}

/// <summary>
/// Semantic validator for A2UI v0.9 component trees, mirroring
/// <c>validateA2UIComponents</c> / <c>validate_a2ui_components</c> in the sibling toolkits.
/// </summary>
/// <remarks>
/// Structural checks (ids, component types, root presence, child references) always run.
/// Catalog checks (component existence, required props) run only when a catalog is supplied.
/// Absolute data-binding checks run unless <c>validateBindings</c> is <see langword="false"/>;
/// relative binding paths are never validated globally because they resolve per item inside
/// repeated templates.
/// </remarks>
public static class A2UIComponentValidator
{
    /// <summary>
    /// Validates a flat A2UI component array against structural rules and, optionally,
    /// a component catalog and a data model.
    /// </summary>
    /// <param name="components">The flat component array. <see langword="null"/> or empty fails validation.</param>
    /// <param name="data">The surface data model used to resolve absolute binding paths.</param>
    /// <param name="catalog">The component catalog enabling semantic checks.</param>
    /// <param name="validateBindings">
    /// When <see langword="false"/>, absolute binding checks are deferred (used while the data
    /// model has not finished streaming).
    /// </param>
    /// <returns>The validation outcome.</returns>
    public static A2UIValidationResult Validate(
        JsonArray? components,
        JsonObject? data = null,
        A2UIValidationCatalog? catalog = null,
        bool validateBindings = true)
    {
        // Fail loud on a missing/empty payload.
        if (components is null || components.Count == 0)
        {
            return new A2UIValidationResult(false,
            [
                new A2UIValidationError(
                    A2UIValidationErrorCodes.EmptyComponents,
                    "components",
                    "A2UI components must be a non-empty array"),
            ]);
        }

        List<A2UIValidationError> errors = [];

        // First pass: collect ids and flag duplicates.
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonNode? node in components)
        {
            if (node is JsonObject component && component["id"] is JsonValue idValue &&
                idValue.TryGetValue(out string? id) && !ids.Add(id))
            {
                errors.Add(new A2UIValidationError(
                    A2UIValidationErrorCodes.DuplicateId,
                    $"components[id={id}]",
                    $"Duplicate component id '{id}'"));
            }
        }

        for (int i = 0; i < components.Count; i++)
        {
            JsonObject? component = components[i] as JsonObject;
            string? id = TryGetString(component?["id"]);
            string? componentType = TryGetString(component?["component"]);

            if (string.IsNullOrEmpty(id))
            {
                errors.Add(new A2UIValidationError(
                    A2UIValidationErrorCodes.MissingId,
                    $"components[{i}].id",
                    $"Component at index {i} is missing a string 'id'"));
            }

            if (string.IsNullOrEmpty(componentType))
            {
                errors.Add(new A2UIValidationError(
                    A2UIValidationErrorCodes.MissingComponentType,
                    $"components[{i}].component",
                    $"Component at index {i} is missing a string 'component' type"));
            }

            if (catalog is not null && componentType is not null)
            {
                if (catalog.Components[componentType] is not JsonObject schema)
                {
                    errors.Add(new A2UIValidationError(
                        A2UIValidationErrorCodes.UnknownComponent,
                        $"components[{i}].component",
                        $"Component type '{componentType}' is not in the catalog"));
                }
                else if (schema["required"] is JsonArray required)
                {
                    foreach (JsonNode? requiredNode in required)
                    {
                        if (TryGetString(requiredNode) is string requiredProp &&
                            component?.ContainsKey(requiredProp) != true)
                        {
                            errors.Add(new A2UIValidationError(
                                A2UIValidationErrorCodes.MissingRequiredProp,
                                $"components[{i}].{requiredProp}",
                                $"Component '{componentType}' (index {i}) is missing required prop '{requiredProp}'"));
                        }
                    }
                }
            }

            if (component is not null)
            {
                foreach (string reference in CollectChildReferences(component["children"]))
                {
                    if (!ids.Contains(reference))
                    {
                        errors.Add(new A2UIValidationError(
                            A2UIValidationErrorCodes.UnresolvedChild,
                            $"components[{i}].children",
                            $"Child reference '{reference}' does not match any component id"));
                    }
                }

                if (validateBindings)
                {
                    List<string> bindingPaths = [];
                    CollectAbsoluteBindingPaths(component, bindingPaths);
                    foreach (string path in bindingPaths)
                    {
                        if (!AbsolutePathResolves(path, data))
                        {
                            errors.Add(new A2UIValidationError(
                                A2UIValidationErrorCodes.UnresolvedBinding,
                                $"components[{i}]",
                                $"Binding path '{path}' does not resolve in the data model"));
                        }
                    }
                }
            }
        }

        bool hasRoot = false;
        foreach (JsonNode? node in components)
        {
            if (node is JsonObject component && TryGetString(component["id"]) == "root")
            {
                hasRoot = true;
                break;
            }
        }

        if (!hasRoot)
        {
            errors.Add(new A2UIValidationError(
                A2UIValidationErrorCodes.NoRoot,
                "components",
                "No component has id 'root'"));
        }

        return new A2UIValidationResult(errors.Count == 0, errors);
    }

    private static string? TryGetString(JsonNode? node)
        => node is JsonValue value && value.TryGetValue(out string? text) ? text : null;

    private static bool AbsolutePathResolves(string path, JsonNode? data)
    {
        JsonNode? cursor = data;
        foreach (string segment in path.Split('/'))
        {
            if (segment.Length == 0)
            {
                continue;
            }

            switch (cursor)
            {
                case JsonArray array:
                    if (!int.TryParse(segment, out int index) || index < 0 || index >= array.Count)
                    {
                        return false;
                    }

                    cursor = array[index];
                    break;

                case JsonObject obj:
                    if (!obj.TryGetPropertyValue(segment, out JsonNode? next))
                    {
                        return false;
                    }

                    cursor = next;
                    break;

                default:
                    return false;
            }
        }

        return true;
    }

    private static List<string> CollectChildReferences(JsonNode? children)
    {
        List<string> references = [];

        void Push(JsonNode? node)
        {
            if (TryGetString(node) is string id)
            {
                references.Add(id);
            }
            else if (node is JsonObject obj && TryGetString(obj["componentId"]) is string componentId)
            {
                references.Add(componentId);
            }
        }

        if (children is JsonArray array)
        {
            foreach (JsonNode? child in array)
            {
                Push(child);
            }
        }
        else if (children is JsonObject)
        {
            Push(children);
        }

        return references;
    }

    private static void CollectAbsoluteBindingPaths(JsonNode? node, List<string> accumulator)
    {
        switch (node)
        {
            case JsonArray array:
                foreach (JsonNode? item in array)
                {
                    CollectAbsoluteBindingPaths(item, accumulator);
                }

                break;

            case JsonObject obj:
                if (TryGetString(obj["path"]) is string path && path.Length > 0 && path[0] == '/')
                {
                    accumulator.Add(path);
                }

                foreach (KeyValuePair<string, JsonNode?> property in obj)
                {
                    if (!string.Equals(property.Key, "path", StringComparison.Ordinal))
                    {
                        CollectAbsoluteBindingPaths(property.Value, accumulator);
                    }
                }

                break;

            default:
                break;
        }
    }
}
