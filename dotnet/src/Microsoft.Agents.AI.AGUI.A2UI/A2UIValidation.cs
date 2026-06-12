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

    /// <summary>A component participates in a child-reference cycle; the child/children tree must be a DAG.</summary>
    public const string ChildCycle = "child_cycle";

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
    /// <summary>The component fields that carry child references: singular <c>child</c> and plural <c>children</c>.</summary>
    private static readonly string[] s_childReferenceFields = ["child", "children"];

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

        // First pass: collect ids and flag duplicates. Empty ids are skipped here so they
        // are reported once as a missing id in the next pass rather than as spurious
        // duplicates of each other.
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonNode? node in components)
        {
            if (node is JsonObject component && component["id"] is JsonValue idValue &&
                idValue.TryGetValue(out string? id) && !string.IsNullOrEmpty(id) && !ids.Add(id))
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
                // Validate both the singular `child` (one-child containers such as Card and
                // Button, which the default prompt uses) and the plural `children` so a
                // dangling reference in either is caught and fed back to the recovery loop.
                foreach (string field in s_childReferenceFields)
                {
                    foreach (string reference in CollectChildReferences(component[field]))
                    {
                        if (!ids.Contains(reference))
                        {
                            errors.Add(new A2UIValidationError(
                                A2UIValidationErrorCodes.UnresolvedChild,
                                $"components[{i}].{field}",
                                $"Child reference '{reference}' does not match any component id"));
                        }
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

        // The child/children tree must be a DAG — a component that (transitively)
        // references itself never terminates at render time. Report each cycle once.
        foreach (List<string> cycle in FindChildCycles(components))
        {
            errors.Add(new A2UIValidationError(
                A2UIValidationErrorCodes.ChildCycle,
                $"components[id={cycle[0]}]",
                $"Child reference cycle detected: {string.Join(" -> ", cycle)} -> {cycle[0]}"));
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
        else if (children is JsonObject or JsonValue)
        {
            // A JsonObject template ({ componentId, ... }) or a bare string id (the singular
            // `child` shape).
            Push(children);
        }

        return references;
    }

    /// <summary>id → ordered child-id references, gathered from singular <c>child</c> + plural <c>children</c>.</summary>
    private static Dictionary<string, List<string>> BuildChildAdjacency(JsonArray components)
    {
        var adjacency = new Dictionary<string, List<string>>(StringComparer.Ordinal);
        foreach (JsonNode? node in components)
        {
            if (node is JsonObject component && TryGetString(component["id"]) is string id)
            {
                List<string> references = [];
                foreach (string field in s_childReferenceFields)
                {
                    references.AddRange(CollectChildReferences(component[field]));
                }

                adjacency[id] = references;
            }
        }

        return adjacency;
    }

    /// <summary>
    /// Finds unique child-reference cycles (self-references and longer loops) over the child graph
    /// via an iterative depth-first search. The traversal is explicit-stack rather than recursive
    /// so a pathologically deep child chain in untrusted model output cannot overflow the call
    /// stack (an uncatchable failure on .NET). Each cycle is canonicalised — rotated so the
    /// lexicographically smallest id leads — so the same loop reached from different entry points
    /// collapses to one finding, and the reported chain stays byte-identical across the sibling
    /// toolkits.
    /// </summary>
    private static List<List<string>> FindChildCycles(JsonArray components)
    {
        Dictionary<string, List<string>> adjacency = BuildChildAdjacency(components);
        var color = new Dictionary<string, int>(StringComparer.Ordinal); // absent/0 = unvisited, 1 = on path, 2 = done
        var seenKeys = new HashSet<string>(StringComparer.Ordinal);
        var cycles = new List<List<string>>();

        // path = the ids currently on the DFS path (the "on path"/grey set, in order).
        // frames = a resumable DFS frame per path node: which neighbor index to visit next.
        var path = new List<string>();
        var frames = new Stack<(string Node, int NextNeighbor)>();

        foreach (string id in adjacency.Keys)
        {
            if (color.TryGetValue(id, out int rootState) && rootState != 0)
            {
                continue;
            }

            color[id] = 1;
            path.Add(id);
            frames.Push((id, 0));

            while (frames.Count > 0)
            {
                (string u, int next) = frames.Pop();
                List<string> neighbors = adjacency.TryGetValue(u, out List<string>? n) ? n : [];

                bool descended = false;
                for (int i = next; i < neighbors.Count; i++)
                {
                    string v = neighbors[i];
                    int state = color.TryGetValue(v, out int c) ? c : 0;
                    if (state == 1)
                    {
                        // Back-edge to a node still on the path: extract the loop.
                        int start = path.IndexOf(v);
                        List<string> cycle = Canonicalize(path.GetRange(start, path.Count - start));
                        if (seenKeys.Add(string.Join(" ", cycle)))
                        {
                            cycles.Add(cycle);
                        }
                    }
                    else if (state == 0)
                    {
                        // Descend into v, resuming u after this neighbor on the way back up.
                        frames.Push((u, i + 1));
                        color[v] = 1;
                        path.Add(v);
                        frames.Push((v, 0));
                        descended = true;
                        break;
                    }
                }

                if (!descended)
                {
                    // u is fully explored; it is the top of the path.
                    color[u] = 2;
                    path.RemoveAt(path.Count - 1);
                }
            }
        }

        return cycles;
    }

    /// <summary>Rotates a cycle's node list so the lexicographically smallest (ordinal) id leads.</summary>
    private static List<string> Canonicalize(List<string> nodes)
    {
        int m = 0;
        for (int i = 1; i < nodes.Count; i++)
        {
            if (string.CompareOrdinal(nodes[i], nodes[m]) < 0)
            {
                m = i;
            }
        }

        var rotated = new List<string>(nodes.Count);
        rotated.AddRange(nodes.GetRange(m, nodes.Count - m));
        rotated.AddRange(nodes.GetRange(0, m));
        return rotated;
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
