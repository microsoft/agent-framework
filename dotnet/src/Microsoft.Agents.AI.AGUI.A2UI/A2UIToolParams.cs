// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.AGUI.A2UI;

/// <summary>
/// Shared behavior knobs for A2UI tool factories. Every framework adapter accepts this
/// exact shape, so a new knob reaches all adapters without signature changes.
/// </summary>
/// <remarks>
/// Mirrors <c>A2UIToolParams</c> in the sibling toolkits, minus the <c>model</c> field:
/// in .NET the subagent chat client is a framework concern owned by the adapter's own
/// factory signature, not by this parameter object.
/// </remarks>
public sealed class A2UIToolParams
{
    /// <summary>Gets the prompt-section overrides.</summary>
    public A2UIGuidelines? Guidelines { get; init; }

    /// <summary>Gets the fallback surface id. Empty or unset falls back to <see cref="A2UIConstants.DefaultSurfaceId"/>.</summary>
    public string? DefaultSurfaceId { get; init; }

    /// <summary>Gets the catalog id for created surfaces. Empty or unset falls back to <see cref="A2UIConstants.BasicCatalogId"/>.</summary>
    public string? DefaultCatalogId { get; init; }

    /// <summary>Gets the planner-facing tool name. Empty or unset falls back to <see cref="A2UIConstants.GenerateA2UIToolName"/>.</summary>
    public string? ToolName { get; init; }

    /// <summary>Gets the planner-facing tool description. Empty or unset falls back to the canonical description.</summary>
    public string? ToolDescription { get; init; }

    /// <summary>Gets the catalog used for semantic validation in the recovery loop.</summary>
    public A2UIValidationCatalog? Catalog { get; init; }

    /// <summary>Gets the recovery-loop configuration.</summary>
    public A2UIRecoveryConfig? Recovery { get; init; }

    /// <summary>Gets the per-attempt observability callback.</summary>
    public Action<A2UIAttemptRecord>? OnAttempt { get; init; }
}

/// <summary>
/// <see cref="A2UIToolParams"/> with every defaultable field resolved to its effective value.
/// </summary>
/// <param name="Guidelines">The prompt-section overrides, passed through.</param>
/// <param name="DefaultSurfaceId">The effective fallback surface id.</param>
/// <param name="DefaultCatalogId">The effective default catalog id.</param>
/// <param name="ToolName">The effective planner-facing tool name.</param>
/// <param name="ToolDescription">The effective planner-facing tool description.</param>
/// <param name="Catalog">The validation catalog, passed through.</param>
/// <param name="Recovery">The recovery configuration, passed through.</param>
/// <param name="OnAttempt">The per-attempt callback, passed through.</param>
public sealed record A2UIResolvedToolParams(
    A2UIGuidelines? Guidelines,
    string DefaultSurfaceId,
    string DefaultCatalogId,
    string ToolName,
    string ToolDescription,
    A2UIValidationCatalog? Catalog,
    A2UIRecoveryConfig? Recovery,
    Action<A2UIAttemptRecord>? OnAttempt);

/// <summary>
/// Canonical tool definitions and descriptions shared by all A2UI adapters.
/// </summary>
public static class A2UIToolDefinitions
{
    /// <summary>
    /// Gets the planner-facing description of the <c>generate_a2ui</c> tool.
    /// </summary>
    public static string GenerateA2UIToolDescription =>
        "Generate or update a dynamic A2UI surface based on the conversation. " +
        "A secondary LLM designs the UI components and data. " +
        "Use intent='create' (default) when the user requests new visual content " +
        "(cards, forms, lists, dashboards, comparisons, etc.). " +
        "Use intent='update' with target_surface_id to modify a surface you " +
        "previously rendered (e.g. 'change the second card's price', " +
        "'add a Buy button', 'use red instead of blue').";

    /// <summary>
    /// Gets the planner-facing description of the <c>generate_a2ui</c> tool's <c>intent</c> argument.
    /// </summary>
    public static string IntentArgumentDescription =>
        "'create' to render a new surface; 'update' to modify a surface " +
        "previously rendered in this conversation. Defaults to 'create'.";

    /// <summary>
    /// Gets the planner-facing description of the <c>generate_a2ui</c> tool's
    /// <c>target_surface_id</c> argument.
    /// </summary>
    public static string TargetSurfaceIdArgumentDescription =>
        "Required when intent='update'. The surface id of the prior render to modify.";

    /// <summary>
    /// Gets the planner-facing description of the <c>generate_a2ui</c> tool's <c>changes</c> argument.
    /// </summary>
    public static string ChangesArgumentDescription =>
        "Optional natural-language description of the changes to apply when intent='update'.";

    /// <summary>
    /// Creates the OpenAI-style function definition of the inner <c>render_a2ui</c>
    /// structured-output tool (<c>surfaceId</c>, <c>components</c>, <c>data</c>;
    /// <c>surfaceId</c> and <c>components</c> required).
    /// </summary>
    /// <returns>A fresh, caller-owned <see cref="JsonObject"/> with the tool definition.</returns>
    public static JsonObject CreateRenderA2UIToolDefinition() => new()
    {
        ["type"] = "function",
        ["function"] = new JsonObject
        {
            ["name"] = A2UIConstants.RenderA2UIToolName,
            ["description"] =
                "Render a dynamic A2UI v0.9 surface. The root component must have " +
                "id 'root'. Use components from the available catalog only.",
            ["parameters"] = new JsonObject
            {
                ["type"] = "object",
                ["properties"] = new JsonObject
                {
                    ["surfaceId"] = new JsonObject
                    {
                        ["type"] = "string",
                        ["description"] = "Unique surface identifier.",
                    },
                    ["components"] = new JsonObject
                    {
                        ["type"] = "array",
                        ["description"] =
                            "A2UI v0.9 component array (flat format). The root " +
                            "component must have id 'root'.",
                        ["items"] = new JsonObject { ["type"] = "object" },
                    },
                    ["data"] = new JsonObject
                    {
                        ["type"] = "object",
                        ["description"] =
                            "Optional initial data model for the surface (form " +
                            "values, list items for data-bound components, etc.).",
                    },
                },
                ["required"] = new JsonArray("surfaceId", "components"),
            },
        },
    };

    /// <summary>
    /// Fills canonical defaults for every unset or empty-string field of
    /// <paramref name="parameters"/>. Empty strings fall back to defaults rather than
    /// propagating into tool advertisements or emitted operations.
    /// </summary>
    /// <param name="parameters">The raw parameters, or <see langword="null"/> for all defaults.</param>
    /// <returns>The resolved parameters.</returns>
    public static A2UIResolvedToolParams ResolveA2UIToolParams(A2UIToolParams? parameters) => new(
        Guidelines: parameters?.Guidelines,
        DefaultSurfaceId: DefaultOr(parameters?.DefaultSurfaceId, A2UIConstants.DefaultSurfaceId),
        DefaultCatalogId: DefaultOr(parameters?.DefaultCatalogId, A2UIConstants.BasicCatalogId),
        ToolName: DefaultOr(parameters?.ToolName, A2UIConstants.GenerateA2UIToolName),
        ToolDescription: DefaultOr(parameters?.ToolDescription, GenerateA2UIToolDescription),
        Catalog: parameters?.Catalog,
        Recovery: parameters?.Recovery,
        OnAttempt: parameters?.OnAttempt);

    private static string DefaultOr(string? value, string fallback)
        => string.IsNullOrEmpty(value) ? fallback : value!;
}

/// <summary>
/// The built-in default prompt blocks shared by all adapters. The exact text is part of
/// the cross-language contract and is ported verbatim from the sibling toolkits.
/// </summary>
public static class A2UIPromptDefaults
{
    /// <summary>
    /// Gets the default generation-guidelines block (A2UI protocol rules: ids, paths,
    /// bindings, data model). Ported verbatim from the sibling toolkits.
    /// </summary>
    public static string GenerationGuidelines => """
        Generate A2UI v0.9 JSON.

        ## A2UI Protocol Instructions

        A2UI (Agent to UI) is a protocol for rendering rich UI surfaces from agent responses.

        CRITICAL: You MUST call the render_a2ui tool with ALL of these arguments:
        - surfaceId: A unique ID for the surface (e.g. "product-comparison")
        - components: REQUIRED — the A2UI component array. NEVER omit this. Use a List with
          children: { componentId: "card-id", path: "/items" } for repeating cards.
        - data: OPTIONAL — a JSON object written to the root of the surface data model.
          Use for pre-filling form values or providing data for path-bound components.
        - every component must have the "component" field specifying the component type (e.g. "Text", "Image", "Row", "Column", "List", "Button", etc.)

        COMPONENT ID RULES:
        - Every component ID must be unique within the surface.
        - A component MUST NOT reference itself as child/children. This causes a
          circular dependency error. For example, if a component has id="avatar",
          its child must be a DIFFERENT id (e.g. "avatar-img"), never "avatar".
        - The child/children tree must be a DAG — no cycles allowed.

        PATH RULES FOR TEMPLATES:
        Components inside a repeating List use RELATIVE paths (no leading slash).
        The path is resolved relative to each array item automatically.
        If List has children: { componentId: "card", path: "/items" } and item has key "name",
        use { "path": "name" } (NO leading slash — relative to item).
        CRITICAL: Do NOT use "/name" (absolute) inside templates — use "name" (relative).
        The List's own path ("/items") uses a leading slash (absolute), but all
        components INSIDE the template card use paths WITHOUT leading slash.
        Do NOT use "/items/0/name" or "/items/{@key}/name" — just "name".

        DATA MODEL:
        The "data" key in the tool args is a plain JSON object that initializes the surface
        data model. Components bound to paths (e.g. "value": { "path": "/form/name" })
        read from and write to this data model. Examples:
          For forms:  "data": { "form": { "name": "Alice", "email": "" } }
          For lists:  "data": { "items": [{"name": "Product A"}, {"name": "Product B"}] }
          For mixed:  "data": { "form": { "query": "" }, "results": [...] }

        FORMS AND TWO-WAY DATA BINDING:
        To create editable forms, bind input components to data model paths using { "path": "..." }.
        The client automatically writes user input back to the data model at the bound path.
        CRITICAL: Using a literal value (e.g. "value": "") makes the field READ-ONLY.
        You MUST use { "path": "..." } to make inputs editable.

        All input components use "value" as the binding property:
        - TextField:     "value": { "path": "/form/fieldName" }
        - CheckBox:      "value": { "path": "/form/isChecked" }
        - Slider:        "value": { "path": "/form/sliderVal" }
        - DateTimeInput: "value": { "path": "/form/date" }
        - ChoicePicker:  "value": { "path": "/form/choices" }

        To retrieve form values when a button is clicked, include "context" with path references
        in the button's action. Paths are resolved to their current values at click time:
          "action": { "event": { "name": "submit", "context": { "userName": { "path": "/form/name" } } } }

        To pre-fill form values, pass initial data via the "data" tool argument:
          "data": { "form": { "name": "Markus" } }

        FORM EXAMPLE (editable text field with pre-filled value + submit button):
          "components": [
            { "id": "root", "component": "Card", "child": "form-col" },
            { "id": "form-col", "component": "Column", "children": ["name-field", "submit-row"] },
            { "id": "name-field", "component": "TextField", "label": "Name", "value": { "path": "/form/name" } },
            { "id": "submit-row", "component": "Row", "justify": "end", "children": ["submit-btn"] },
            { "id": "submit-btn", "component": "Button", "child": "btn-text", "variant": "primary",
              "action": { "event": { "name": "submit", "context": { "userName": { "path": "/form/name" } } } } },
            { "id": "btn-text", "component": "Text", "text": "Submit" }
          ],
          "data": { "form": { "name": "Markus" } }
        """;

    /// <summary>
    /// Gets the default design-guidelines block (visual hierarchy, layout patterns).
    /// Ported verbatim from the sibling toolkits.
    /// </summary>
    public static string DesignGuidelines => """
        Create polished, visually appealing interfaces:
        - Always include a title heading (h2) for the surface, outside the List.
          Wrap in a Column: [title, list] as root.
        - For card templates, create clear visual hierarchy:
          - h3 for primary text (names, titles)
          - h2 for featured numbers (prices, scores) — makes them stand out
          - caption for secondary info (ratings, categories, metadata)
          - body for descriptions
        - Use Divider between logical sections within cards.
        - Use Row with justify="spaceBetween" for label-value pairs
          (e.g. "Rating" on left, "4.5/5" on right).
        - Include images when relevant (logos, icons, product photos):
          - Use Image component with variant="smallFeature" or "avatar"
          - Prefer company logos for branded products — Google favicons are reliable:
            https://www.google.com/s2/favicons?domain=sony.com&sz=128
            https://www.google.com/s2/favicons?domain=bose.com&sz=128
          - For generic icons: https://placehold.co/128x128/EEE/999?text=🎧
          - Do NOT invent Unsplash photo-IDs — they will 404. Only use real, known URLs.
        - Use horizontal List direction for side-by-side comparison cards.
        - Keep cards clean — avoid clutter. Whitespace is good.
        - Use consistent surfaceIds (lowercase, hyphenated).
        - NEVER use the same ID for a component and its child — this creates a
          circular dependency. E.g. if id="avatar", child must NOT be "avatar".
        - Both Row and Column support "justify" and "align".
        - Add Button for interactivity. Button needs child (Text ID) + action.
          Action MUST use this exact nested format:
            "action": { "event": { "name": "myAction", "context": { "key": "value" } } }
          The "event" key holds an OBJECT with "name" (required) and "context" (optional).
          Do NOT use a flat format like {"event": "name"} — "event" must be an object.
          Use variant="primary" for main action buttons, variant="borderless" for links.
        - For forms: wrap fields in a Card with a Column. Place the submit button in a
          Row with justify="end". Every input MUST use path binding on the "value" property
          (e.g. "value": { "path": "/form/name" }) to be editable. The submit button's action
          context MUST reference the same paths to capture the user's input.

        Use the SAME surfaceId as the main surface. Match action names to Button action event names.
        """;
}
