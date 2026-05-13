// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;

namespace Microsoft.Agents.AI.Abstractions.IntegrationTests;

/// <summary>
/// Example tools used by the <see cref="MenuConversationTestCase"/> to simulate a restaurant menu service.
/// </summary>
internal static class MenuTools
{
    [Description("Provides a list of today's specials from the restaurant menu.")]
    public static string GetSpecials() =>
        """
        Special Soup: Clam Chowder
        Special Salad: Cobb Salad
        Special Drink: Chai Tea
        """;

    [Description("Provides the price of the requested menu item.")]
    public static string GetItemPrice(
        [Description("The name of the menu item.")] string menuItem) => "$9.99";
}
