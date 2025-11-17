# Copyright (c) Microsoft. All rights reserved.

"""Recipe agent example demonstrating shared state management (Feature 3)."""

from enum import Enum

from agent_framework import ChatAgent, ai_function
from agent_framework._clients import ChatClientProtocol
from pydantic import BaseModel, Field

from agent_framework_ag_ui import AgentFrameworkAgent, RecipeConfirmationStrategy


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
def update_recipe(recipe: Recipe) -> str:
    """Update the recipe with new or modified content.

    You MUST write the complete recipe with ALL fields, even when changing only a few items.
    When modifying an existing recipe, include ALL existing ingredients and instructions plus your changes.
    NEVER delete existing data - only add or modify.

    Args:
        recipe: The complete recipe object with all details

    Returns:
        Confirmation that the recipe was updated
    """
    return "Recipe updated."


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
    )
