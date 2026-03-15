// Copyright (c) Microsoft. All rights reserved.

namespace TutorialApp.Services;

/// <summary>Defines a supported UI language.</summary>
/// <param name="Code">BCP-47 language code (e.g. "en", "pl"). Must match a content/ subdirectory name.</param>
/// <param name="NativeName">Language name shown in the switcher, written in that language.</param>
/// <param name="Flag">Flag emoji for the language (e.g. "🇬🇧").</param>
public record LanguageDef(string Code, string NativeName, string Flag);

/// <summary>
/// Scoped service that tracks the active language for the current Blazor circuit.
/// To add a new language: add an entry to <see cref="Available"/> and create a
/// matching <c>content/{code}/</c> directory with translated markdown files.
/// </summary>
public sealed class LanguageService
{
    // ── Add new languages here ──────────────────────────────────────────────
    public static readonly IReadOnlyList<LanguageDef> Available =
    [
        new("en", "English", "🇬🇧"),
        new("pl", "Polski", "🇵🇱"),
    ];
    // ───────────────────────────────────────────────────────────────────────

    private string _currentCode = Available[0].Code;

    public string CurrentCode => _currentCode;

    public LanguageDef Current => Available.First(l => l.Code == _currentCode);

    public event EventHandler? OnChanged;

    public void SetLanguage(string code)
    {
        if (_currentCode == code) return;
        if (Available.All(l => l.Code != code)) return;
        _currentCode = code;
        OnChanged?.Invoke(this, EventArgs.Empty);
    }
}
