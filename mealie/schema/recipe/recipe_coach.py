from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import UUID4, Field

from mealie.schema._mealie import MealieModel
from mealie.schema.meal_plan.new_meal import PlanEntryType
from mealie.schema.openai._base import OpenAIBase
from mealie.schema.recipe.recipe import RecipeSummary
from mealie.schema.recipe.recipe_ingredient import IngredientFood


class RecipeRevisionOut(MealieModel):
    id: UUID4
    recipe_id: UUID4
    user_id: UUID4
    source: str
    snapshot: dict[str, Any]
    created_at: datetime


class RecipeReviewField(StrEnum):
    description = "description"
    ingredient = "ingredient"
    new_ingredient = "new_ingredient"
    instruction = "instruction"
    new_instruction = "new_instruction"
    note = "note"
    prep_time = "prep_time"
    cook_time = "cook_time"
    total_time = "total_time"
    recipe_yield = "recipe_yield"


class RecipeReviewChange(OpenAIBase):
    field: RecipeReviewField
    index: int | None = None
    original: str | None = None
    replacement: str


class RecipeReviewSuggestion(OpenAIBase):
    category: str
    title: str
    rationale: str
    changes: list[RecipeReviewChange]


class RecipeReviewResponse(OpenAIBase):
    summary: str
    suggestions: list[RecipeReviewSuggestion]


class RecipeReviewRequest(MealieModel):
    goal: str = "Improve flavor, clarity, consistency, and reliability"


class ApplyRecipeReviewRequest(MealieModel):
    suggestions: list[RecipeReviewSuggestion]


class PantryPlanRequest(MealieModel):
    start_date: date
    days: int = Field(default=7, ge=1, le=14)
    max_missing_foods: int = Field(default=3, ge=0, le=10)
    preferences: str = ""


class PantryPlanAIChoice(OpenAIBase):
    # OpenAI structured outputs does not accept Pydantic's nonstandard
    # "uuid4" JSON-schema format. The controller only accepts IDs from its
    # already-filtered candidate map, so a plain string remains safe here.
    recipe_id: str
    date: date
    entry_type: PlanEntryType = PlanEntryType.dinner
    reason: str


class PantryPlanAIResponse(OpenAIBase):
    choices: list[PantryPlanAIChoice]


class PantryPlanSuggestion(MealieModel):
    recipe: RecipeSummary
    date: date
    entry_type: PlanEntryType
    reason: str
    missing_foods: list[IngredientFood]
    unlinked_ingredient_count: int = 0
    makeable: bool


class PantryPlanResponse(MealieModel):
    pantry_foods: list[IngredientFood]
    suggestions: list[PantryPlanSuggestion]
