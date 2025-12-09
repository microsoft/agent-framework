# Copyright (c) Microsoft. All rights reserved.

"""Recipe agent example demonstrating shared state management (Feature 3)."""

from enum import Enum

from agent_framework import ChatAgent, ChatClientProtocol, ai_function
from agent_framework.ag_ui import AgentFrameworkAgent, RecipeConfirmationStrategy
from pydantic import BaseModel, Field


class SkillLevel(str, Enum):
    """The skill level required for the recipe."""

    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class CookingTime(str, Enum):
    """The cooking time of the recipe."""

    FIVE_MIN = "5 min"
    FIFTEEN_MIN = "15 min"
    THIRTY_MIN = "30 min"
    FORTY_FIVE_MIN = "45 min"
    SIXTY_PLUS_MIN = "60+ min"


class Ingredient(BaseModel):
    """An ingredient with its details."""

    icon: str = Field(..., description="Emoji icon representing the ingredient (e.g., 🥕)")
    name: str = Field(..., description="Name of the ingredient")
    amount: str = Field(..., description="Amount or quantity of the ingredient")


class Recipe(BaseModel):
    """A complete recipe."""

    title: str = Field(..., description="The title of the recipe")
    skill_level: SkillLevel = Field(..., description="The skill level required")
    special_preferences: list[str] = Field(
        default_factory=list, description="Dietary preferences (e.g., Vegetarian, Gluten-free)"
    )
    cooking_time: CookingTime = Field(..., description="The estimated cooking time")
    ingredients: list[Ingredient] = Field(..., description="Complete list of ingredients")
    instructions: list[str] = Field(..., description="Step-by-step cooking instructions")


@ai_function
def update_recipe(
    recipe: Recipe,
    current_special_preferences: list[str] | None = None,
    user_selected_preferences: list[str] | None = None,
    instruction: str | None = None
) -> str:
    """Update the recipe with new or modified content.

    You MUST write the complete recipe with ALL fields, even when changing only a few items.
    When modifying an existing recipe, include ALL existing ingredients and instructions plus your changes.
    NEVER delete existing data - only add or modify.

    Args:
        recipe: The complete recipe object with all details
        current_special_preferences: The agent's current preferences (for comparison)
        user_selected_preferences: The user's desired preferences (for prompt generation)
        instruction: Optional explicit instruction (if provided, use it directly)

    Returns:
        Confirmation that the recipe was updated
    """
    # Generate intelligent prompt if not provided
    if not instruction and current_special_preferences is not None and user_selected_preferences is not None:
        instruction = _generate_preference_instruction(current_special_preferences, user_selected_preferences)
        print(f"Generated instruction: {instruction}")

    # In a real implementation, this would save the recipe
    # For now, just return confirmation
    if instruction:
        return f"Recipe updated. Instruction: {instruction}"
    return "Recipe updated."


def _extract_preferences_from_message(message_content: str) -> tuple[list[str] | None, list[str] | None]:
    """Extract current and desired preferences from message content.

    Args:
        message_content: The message content to parse

    Returns:
        Tuple of (current_preferences, desired_preferences) or (None, None) if not found
    """
    import re

    # Try to find Preference Comparison section
    comparison_match = re.search(
        r'Preference Comparison:\s*\nCurrent \(agent\):\s*(\[.*?\])\s*\nDesired \(user\):\s*(\[.*?\])',
        message_content,
        re.DOTALL
    )

    if comparison_match:
        try:
            import json
            current = json.loads(comparison_match.group(1))
            desired = json.loads(comparison_match.group(2))
            return current, desired
        except:
            pass

    # Try to find special_preferences in recipe JSON
    recipe_match = re.search(r'"special_preferences":\s*(\[.*?\])', message_content, re.DOTALL)
    if recipe_match:
        try:
            import json
            desired = json.loads(recipe_match.group(1))
            return None, desired  # Only desired found
        except:
            pass

    return None, None


def _generate_preference_instruction(current: list[str], desired: list[str]) -> str:
    """Generate intelligent instruction by comparing current vs desired preferences.

    Args:
        current: Current special_preferences from agent
        desired: User's desired special_preferences

    Returns:
        Natural language instruction following the agent's instruction patterns
    """
    if not current:
        current = []
    if not desired:
        desired = []

    # Find differences
    to_add = [p for p in desired if p not in current]
    to_remove = [p for p in current if p not in desired]
    unchanged = [p for p in current if p in desired]

    # Generate instruction based on changes
    instruction_parts = []

    if to_add and to_remove:
        # Both adding and removing - generate combined instruction
        removed_str = ", ".join(to_remove)
        added_str = ", ".join(to_add)

        if len(to_remove) == 1 and len(to_add) == 1:
            # Simple swap
            instruction_parts.append(f"Change from {removed_str} to {added_str}")
            instruction_parts.append(f"Make it {added_str.lower()} but without {removed_str.lower()}")
        else:
            # Complex changes
            instruction_parts.append(f"Update dietary preferences: remove {removed_str}, add {added_str}")
            instruction_parts.append(f"Make it {', '.join(added_str)} but exclude {removed_str}")
    elif to_add:
        # Only adding
        added_str = ", ".join(to_add)
        if len(to_add) == 1:
            instruction_parts.append(f"Add {added_str} preference")
            instruction_parts.append(f"Make it {added_str.lower()}")
        else:
            instruction_parts.append(f"Add dietary preferences: {added_str}")
            instruction_parts.append(f"Make it {', '.join(added_str)}")
    elif to_remove:
        # Only removing
        removed_str = ", ".join(to_remove)
        if len(to_remove) == 1:
            instruction_parts.append(f"Remove {removed_str} preference")
            instruction_parts.append(f"Make it without {removed_str.lower()}")
        else:
            instruction_parts.append(f"Remove dietary preferences: {removed_str}")
            instruction_parts.append(f"Exclude {removed_str}")
    else:
        # No changes needed
        return "Maintain current dietary preferences"

    return ". ".join(instruction_parts)


_RECIPE_INSTRUCTIONS = """You are a helpful recipe assistant that creates and modifies recipes.

    CRITICAL RULES:
    1. You will receive the current recipe state in the system context
    2. To update the recipe, you MUST use the update_recipe tool
    3. When modifying a recipe, ALWAYS include ALL existing data plus your changes in the tool call
    4. NEVER delete existing ingredients or instructions - only add or modify
    5. After calling the tool, provide a brief conversational message (1-2 sentences)

    When creating a NEW recipe:
    - Provide all required fields: title, skill_level, cooking_time, ingredients, instructions
    - Use actual emojis for ingredient icons (🥕 🧄 🧅 🍅 🌿 🍗 🥩 🧀)
    - Leave special_preferences empty unless specified
    - Message: "Here's your recipe!" or similar

    When MODIFYING or IMPROVING an existing recipe:
    - Include ALL existing ingredients + any new ones
    - Include ALL existing instructions + any new/modified ones
    - Update other fields as needed
    - Message: Explain what you improved (e.g., "I upgraded the ingredients to premium quality")
    - When asked to "improve", enhance with:
      * Better ingredients (upgrade quality, add complementary flavors)
      * More detailed instructions
      * Professional techniques
      * Adjust skill_level if complexity changes
      * Add relevant special_preferences

    SPECIAL PREFERENCES HANDLING - AUTOMATIC INTELLIGENCE:
    The update_recipe tool accepts these parameters:
    - recipe: The complete recipe object
    - current_special_preferences: Your current preferences (extract from your state)
    - user_selected_preferences: User's desired preferences (extract from message)
    - instruction: Generated prompt (tool will generate automatically if not provided)

    EXTRACTION FROM MESSAGE:
    Look for "Preference Comparison" section in user messages:
    ```
    Preference Comparison:
    Current (agent): ["Vegan"]
    Desired (user): ["Spicy"]
    ```
    Or extract "special_preferences" from the recipe JSON in the message.

    TOOL CALLING:
    When you call update_recipe, extract preferences and pass them:
    ```python
    # Get current preferences from your state
    current = self.state.get("recipe", {}).get("special_preferences", [])

    # Extract desired from message
    current_pref, desired_pref = _extract_preferences_from_message(user_message)

    # Call tool with all parameters
    update_recipe(
        recipe=updated_recipe,
        current_special_preferences=current,
        user_selected_preferences=desired_pref
    )
    ```

    INTELLIGENT PROMPT GENERATION:
    The tool will automatically generate instructions by comparing current vs desired:
    - Current: [], Desired: ["Spicy"] → "Add Spicy preference. Make it spicy"
    - Current: ["Vegan"], Desired: [] → "Remove Vegan preference. Make it without vegan"
    - Current: ["Vegan"], Desired: ["Spicy"] → "Change from Vegan to Spicy. Make it spicy but without vegan"

    IMPORTANT for special_preferences (when generating your own instructions):
    - When user says "no X", "remove X", or "without X", EXCLUDE X from special_preferences
    - When user says "add X" or "include X", include X in special_preferences
    - When user says "X only" or "just X", include X but exclude other conflicting preferences
    - Common dietary preferences: High Protein, Low Carb, Spicy, Budget-Friendly, One-Pot Meal, Vegetarian, Vegan

    Example improvements:
    - Upgrade "chicken" → "organic free-range chicken breast"
    - Add herbs: basil, oregano, thyme
    - Add aromatics: garlic, shallots
    - Add finishing touches: lemon zest, fresh parsley
    - Make instructions more detailed and professional
    """


def recipe_agent(chat_client: ChatClientProtocol) -> AgentFrameworkAgent:
    """Create a recipe agent with streaming state updates.

    Args:
        chat_client: The chat client to use for the agent

    Returns:
        A configured AgentFrameworkAgent instance with recipe management
    """
    agent = ChatAgent(
        name="recipe_agent",
        instructions=_RECIPE_INSTRUCTIONS,
        chat_client=chat_client,
        tools=[update_recipe],
    )

    return AgentFrameworkAgent(
        agent=agent,
        name="RecipeAgent",
        description="Creates and modifies recipes with streaming state updates",
        state_schema={
            "recipe": {"type": "object", "description": "The current recipe"},
        },
        predict_state_config={
            "recipe": {"tool": "update_recipe", "tool_argument": "recipe"},
        },
        confirmation_strategy=RecipeConfirmationStrategy(),
        require_confirmation=False,
    )
