// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.SemanticKernel;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;

public sealed class MenuPlugin
{
    public IEnumerable<AIFunction> GetTools()
    {
        yield return AIFunctionFactory.Create(this.GetMenu, name: $"{nameof(MenuPlugin)}_{nameof(GetMenu)}");
        yield return AIFunctionFactory.Create(this.GetSpecials, name: $"{nameof(MenuPlugin)}_{nameof(GetSpecials)}");
        yield return AIFunctionFactory.Create(this.GetItemPrice, name: $"{nameof(MenuPlugin)}_{nameof(GetItemPrice)}");
    }

    [KernelFunction, Description("Provides a list items on the menu.")]
    public MenuItem[] GetMenu()
    {
        return s_menuItems;
    }

    [KernelFunction, Description("Provides a list of specials from the menu.")]
    public MenuItem[] GetSpecials()
    {
        return [.. s_menuItems.Where(i => i.IsSpecial)];
    }

    [KernelFunction, Description("Provides the price of the requested menu item.")]
    public float? GetItemPrice(
        [Description("The name of the menu item.")]
        string name)
    {
        return s_menuItems.FirstOrDefault(i => i.Name.Equals(name, StringComparison.OrdinalIgnoreCase))?.Price;
    }

    private static readonly MenuItem[] s_menuItems =
        [
            new()
            {
                Category = "Soup",
                Name = "Clam Chowder",
                Price = 4.95f,
                IsSpecial = true,
            },
            new()
            {
                Category = "Soup",
                Name = "Tomato Soup",
                Price = 4.95f,
                IsSpecial = false,
            },
            new()
            {
                Category = "Salad",
                Name = "Cobb Salad",
                Price = 9.99f,
            },
            new()
            {
                Category = "Salad",
                Name = "House Salad",
                Price = 4.95f,
            },
            new()
            {
                Category = "Drink",
                Name = "Chai Tea",
                Price = 2.95f,
                IsSpecial = true,
            },
            new()
            {
                Category = "Drink",
                Name = "Soda",
                Price = 1.95f,
            },
        ];

    public sealed class MenuItem
    {
        public string Category { get; init; } = string.Empty;
        public string Name { get; init; } = string.Empty;
        public float Price { get; init; }
        public bool IsSpecial { get; init; }
    }
}
