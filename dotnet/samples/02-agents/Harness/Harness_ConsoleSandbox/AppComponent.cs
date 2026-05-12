// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveComponents;
using Harness.ConsoleReactiveFramework;

namespace Harness.ConsoleSandbox;

/// <summary>
/// Determines which component is shown in the bottom panel.
/// </summary>
public enum BottomPanelMode
{
    /// <summary>Show the list selection component.</summary>
    ListSelection,

    /// <summary>Show the text input component.</summary>
    TextInput
}

public record AppComponentProps : ConsoleReactiveProps
{
    public IReadOnlyList<string> Items { get; init; } = Array.Empty<string>();
    public IReadOnlyList<object> ScrollItems { get; init; } = [];

    /// <summary>Gets the bottom panel mode.</summary>
    public BottomPanelMode Mode { get; init; } = BottomPanelMode.ListSelection;

    /// <summary>Gets the prompt string for text input mode.</summary>
    public string Prompt { get; init; } = "> ";

    /// <summary>Gets the placeholder text shown when the input is empty.</summary>
    public string Placeholder { get; init; } = "";

    /// <summary>Gets the highlight color for the active list item. Defaults to <see cref="ConsoleColor.Cyan"/>.</summary>
    public ConsoleColor ListHighlightColor { get; init; } = ConsoleColor.Cyan;

    /// <summary>Gets the placeholder text for the custom text input option in the list. If <c>null</c>, no custom option is shown.</summary>
    public string? ListCustomTextPlaceholder { get; init; }

    /// <summary>Gets the foreground color for the rule borders. If <c>null</c>, uses the default terminal color.</summary>
    public ConsoleColor? RuleColor { get; init; }
}

/// <summary>
/// Internal state for the <see cref="AppComponent"/>.
/// </summary>
public record AppComponentState : ConsoleReactiveState
{
    /// <summary>Gets the selected index in list selection mode.</summary>
    public int SelectedIndex { get; init; }

    /// <summary>Gets the current input text being typed in text input mode.</summary>
    public string InputText { get; init; } = "";

    /// <summary>Gets the current text being typed into the list's custom text option.</summary>
    public string ListInputText { get; init; } = "";
}

public class AppComponent : ConsoleReactiveComponent<AppComponentProps, AppComponentState>
{
    private readonly TopBottomRule _rule = new();
    private readonly ListSelection _listSelection = new();
    private readonly TextInput _textInput = new();
    private readonly TextScrollPanel _textScrollPanel;
    private readonly TextPanel _textPanel;
    private readonly Func<object, string> _renderItem;
    private readonly Action<string> _onTextInputSubmit;
    private readonly Action<string> _onListInputSubmit;
    private bool _resizedSinceLastRender;
    private int _lastScrollBottom;

    /// <summary>
    /// Initializes a new instance of the <see cref="AppComponent"/> class.
    /// </summary>
    /// <param name="renderScrollItem">A delegate that renders a single scroll panel item and returns the text to display.</param>
    /// <param name="onTextInputSubmit">A callback invoked with the input text when the user presses Enter in text input mode.</param>
    /// <param name="onListInputSubmit">A callback invoked with the selected or typed text when the user presses Enter in list selection mode.</param>
    public AppComponent(Func<object, string> renderScrollItem, Action<string> onTextInputSubmit, Action<string> onListInputSubmit)
    {
        this._renderItem = renderScrollItem;
        this._onTextInputSubmit = onTextInputSubmit;
        this._onListInputSubmit = onListInputSubmit;
        this._textScrollPanel = new TextScrollPanel(renderScrollItem);
        this._textPanel = new TextPanel(renderScrollItem);
        this.State = new AppComponentState();
        KeyEventListener.Instance.KeyPressed += this.OnKeyPressed;
        ConsoleResizeListener.Instance.ConsoleResized += this.OnConsoleResized;
    }

    private void OnKeyPressed(object? sender, KeyPressEventArgs e)
    {
        if (this.Props!.Mode == BottomPanelMode.TextInput)
        {
            this.HandleTextInputKey(e);
        }
        else
        {
            this.HandleListSelectionKey(e);
        }
    }

    private void HandleTextInputKey(KeyPressEventArgs e)
    {
        if (e.KeyInfo.Key == ConsoleKey.Enter)
        {
            string text = this.State!.InputText;
            this.SetState(this.State with { InputText = "" });
            this._onTextInputSubmit(text);
        }
        else if (e.KeyInfo.Key == ConsoleKey.Backspace)
        {
            if (this.State!.InputText.Length > 0)
            {
                this.SetState(this.State with { InputText = this.State.InputText[..^1] });
            }
        }
        else if (e.KeyInfo.KeyChar != '\0' && !char.IsControl(e.KeyInfo.KeyChar))
        {
            this.SetState(this.State! with { InputText = this.State.InputText + e.KeyInfo.KeyChar });
        }
    }

    private void HandleListSelectionKey(KeyPressEventArgs e)
    {
        int maxIndex = this.Props!.Items.Count - 1;
        if (this.Props.ListCustomTextPlaceholder != null)
        {
            maxIndex = this.Props.Items.Count; // extra option at the end
        }

        bool isOnCustomTextOption = this.Props.ListCustomTextPlaceholder != null
            && this.State!.SelectedIndex == this.Props.Items.Count;

        if (e.KeyInfo.Key == ConsoleKey.UpArrow)
        {
            this.SetState(this.State! with { SelectedIndex = Math.Max(0, this.State.SelectedIndex - 1) });
        }
        else if (e.KeyInfo.Key == ConsoleKey.DownArrow)
        {
            this.SetState(this.State! with { SelectedIndex = Math.Min(maxIndex, this.State.SelectedIndex + 1) });
        }
        else if (e.KeyInfo.Key == ConsoleKey.Enter)
        {
            if (isOnCustomTextOption)
            {
                string text = this.State!.ListInputText;
                this.SetState(this.State with { ListInputText = "" });
                this._onListInputSubmit(text);
            }
            else
            {
                this._onListInputSubmit(this.Props.Items[this.State!.SelectedIndex]);
            }
        }
        else if (isOnCustomTextOption)
        {
            // Typing only works when on the custom text option
            if (e.KeyInfo.Key == ConsoleKey.Backspace)
            {
                if (this.State!.ListInputText.Length > 0)
                {
                    this.SetState(this.State with { ListInputText = this.State.ListInputText[..^1] });
                }
            }
            else if (e.KeyInfo.KeyChar != '\0' && !char.IsControl(e.KeyInfo.KeyChar))
            {
                this.SetState(this.State! with { ListInputText = this.State.ListInputText + e.KeyInfo.KeyChar });
            }
        }
    }

    private void OnConsoleResized(object? sender, ConsoleResizeEventArgs e)
    {
        this._resizedSinceLastRender = true;
        this.Render();
    }

    public override void RenderCore(AppComponentProps props, AppComponentState state)
    {
        // Determine the text panel height for the last scroll item
        object? lastItem = props.ScrollItems.Count > 0 ? props.ScrollItems[^1] : null;
        IReadOnlyList<object> lastItems = lastItem != null ? [lastItem] : [];
        int textPanelHeight = TextPanel.CalculateHeight(lastItems, this._renderItem);
        if (textPanelHeight > 0)
        {
            textPanelHeight++; // Extra line for spacing between text panel and rule
        }

        // Build the bottom panel child based on mode
        ConsoleReactiveComponent bottomChild;
        int bottomChildHeight;

        if (props.Mode == BottomPanelMode.TextInput)
        {
            var textInputProps = new TextInputProps
            {
                Prompt = props.Prompt,
                Text = state.InputText,
                Placeholder = props.Placeholder
            };

            bottomChildHeight = TextInput.CalculateHeight(textInputProps, Console.WindowWidth);
            this._textInput.Width = Console.WindowWidth;
            this._textInput.Height = bottomChildHeight;
            this._textInput.Props = textInputProps;
            bottomChild = this._textInput;
        }
        else
        {
            var listProps = new ListSelectionProps
            {
                Items = props.Items,
                SelectedIndex = state.SelectedIndex,
                HighlightColor = props.ListHighlightColor,
                CustomTextPlaceholder = props.ListCustomTextPlaceholder,
                CustomText = state.ListInputText
            };

            bottomChildHeight = ListSelection.CalculateHeight(listProps);
            this._listSelection.Height = bottomChildHeight;
            this._listSelection.Props = listProps;
            bottomChild = this._listSelection;
        }

        var ruleProps = new TopBottomRuleProps
        {
            Width = Console.WindowWidth,
            Color = props.RuleColor,
            Children = [bottomChild]
        };

        int ruleHeight = TopBottomRule.CalculateHeight(ruleProps);
        int scrollBottom = Console.WindowHeight - ruleHeight - textPanelHeight;

        // If scroll region changed or a clear is needed, reset everything
        if (this._resizedSinceLastRender || (this._lastScrollBottom != 0 && scrollBottom != this._lastScrollBottom))
        {
            Console.Write(AnsiEscapes.EraseEntireScreen);
            Console.Write(AnsiEscapes.EraseScrollbackBuffer);
            this._textScrollPanel.Reset();
            this._resizedSinceLastRender = false;
        }

        this._lastScrollBottom = scrollBottom;

        Console.Write(AnsiEscapes.SetScrollRegion(scrollBottom));

        // Render text scroll panel in the scroll area (all items except the last)
        IReadOnlyList<object> scrollItems = props.ScrollItems.Count > 1
            ? props.ScrollItems.Take(props.ScrollItems.Count - 1).ToList()
            : [];

        this._textScrollPanel.X = 1;
        this._textScrollPanel.Y = 1;
        this._textScrollPanel.Width = Console.WindowWidth;
        this._textScrollPanel.Height = scrollBottom;
        this._textScrollPanel.Props = new TextScrollPanelProps
        {
            Items = scrollItems
        };
        this._textScrollPanel.Render();

        // Render the text panel for the last (dynamic) item just below the scroll region
        this._textPanel.X = 1;
        this._textPanel.Y = scrollBottom + 1;
        this._textPanel.Width = Console.WindowWidth;
        this._textPanel.Height = textPanelHeight;
        this._textPanel.Props = new TextPanelProps
        {
            Items = lastItems,
        };
        this._textPanel.Render();

        // Render the bottom rule + child below the text panel
        this._rule.X = 1;
        this._rule.Y = scrollBottom + textPanelHeight + 1;
        this._rule.Props = ruleProps;
        this._rule.Render();

        // Position cursor for natural typing appearance
        if (props.Mode == BottomPanelMode.TextInput)
        {
            int promptLength = props.Prompt.Length;
            int textWidth = Console.WindowWidth - promptLength;
            int textLength = state.InputText.Length;

            // The TextInput starts at rule.Y + 1 (first row inside the rule)
            int textInputY = this._rule.Y + 1;

            if (textWidth <= 0 || textLength == 0)
            {
                // Cursor right after the prompt
                Console.Write(AnsiEscapes.MoveCursor(textInputY, promptLength + 1));
            }
            else
            {
                // Calculate which row and column the cursor lands on
                int cursorRow = textLength < textWidth ? 0 : 1 + ((textLength - textWidth) / textWidth);
                int cursorCol = textLength < textWidth ? textLength : (textLength - textWidth) % textWidth;
                Console.Write(AnsiEscapes.MoveCursor(textInputY + cursorRow, promptLength + cursorCol + 1));
            }
        }
        else if (props.Mode == BottomPanelMode.ListSelection
            && props.ListCustomTextPlaceholder != null
            && state.SelectedIndex == props.Items.Count)
        {
            // Cursor after the typed text in the custom text option
            // The custom text option is at rule.Y + 1 + Items.Count (0-based row inside rule)
            int customOptionY = this._rule.Y + 1 + props.Items.Count;
            // "> " prefix is 2 chars, then the typed text
            int cursorCol = 2 + state.ListInputText.Length + 1;
            Console.Write(AnsiEscapes.MoveCursor(customOptionY, cursorCol));
        }
    }
}
