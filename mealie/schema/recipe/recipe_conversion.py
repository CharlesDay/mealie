from enum import StrEnum

from pydantic import Field

from mealie.schema._mealie import MealieModel
from mealie.schema.recipe.recipe import Recipe


class RecipeUnitSystem(StrEnum):
    metric = "metric"
    imperial = "imperial"


class RecipeConversionRequest(MealieModel):
    recipe: Recipe
    target: RecipeUnitSystem


class RecipeConversionResponse(MealieModel):
    recipe: Recipe
    conversions: int
    assumptions: list[str] = Field(default_factory=list)
