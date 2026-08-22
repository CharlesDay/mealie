import json

from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_coach import RecipeReviewField, RecipeReviewResponse, RecipeReviewSuggestion
from mealie.schema.recipe.recipe_ingredient import RecipeIngredient
from mealie.schema.recipe.recipe_notes import RecipeNote
from mealie.schema.recipe.recipe_step import RecipeStep
from mealie.services.openai import OpenAIService

from .recipe_service import RecipeServiceBase


class RecipeCoachService(RecipeServiceBase):
    async def review(self, recipe: Recipe, goal: str) -> RecipeReviewResponse:
        ai = OpenAIService(self.repos)
        prompt = ai.get_prompt("recipes.review-recipe")
        message = json.dumps(
            {
                "goal": goal,
                "recipe": recipe.model_dump(
                    mode="json",
                    by_alias=True,
                    include={
                        "name",
                        "description",
                        "recipe_servings",
                        "recipe_yield_quantity",
                        "recipe_yield",
                        "prep_time",
                        "cook_time",
                        "total_time",
                        "recipe_ingredient",
                        "recipe_instructions",
                        "notes",
                    },
                ),
            }
        )
        response = await ai.get_response(prompt, message, response_schema=RecipeReviewResponse)
        if response is None:
            return RecipeReviewResponse(summary="No review was returned.", suggestions=[])
        return response

    @staticmethod
    def _require_index(index: int | None, values: list, field: RecipeReviewField) -> int:
        if index is None or index < 0 or index >= len(values):
            raise ValueError(f"Invalid {field.value} index")
        return index

    @staticmethod
    def _require_current(current: str | None, original: str | None) -> None:
        if original is not None and (current or "") != original:
            raise ValueError("The recipe changed after this AI review was generated. Run the review again.")

    def apply(self, recipe: Recipe, suggestions: list[RecipeReviewSuggestion]) -> Recipe:
        updated = recipe.model_copy(deep=True)
        updated.notes = updated.notes or []
        updated.recipe_instructions = updated.recipe_instructions or []

        for suggestion in suggestions:
            for change in suggestion.changes:
                if change.field == RecipeReviewField.description:
                    self._require_current(updated.description, change.original)
                    updated.description = change.replacement
                elif change.field == RecipeReviewField.ingredient:
                    index = self._require_index(change.index, updated.recipe_ingredient, change.field)
                    ingredient = updated.recipe_ingredient[index]
                    self._require_current(ingredient.note, change.original)
                    ingredient.note = change.replacement
                elif change.field == RecipeReviewField.new_ingredient:
                    updated.recipe_ingredient.append(RecipeIngredient(note=change.replacement))
                elif change.field == RecipeReviewField.instruction:
                    index = self._require_index(change.index, updated.recipe_instructions, change.field)
                    instruction = updated.recipe_instructions[index]
                    self._require_current(instruction.text, change.original)
                    instruction.text = change.replacement
                elif change.field == RecipeReviewField.new_instruction:
                    updated.recipe_instructions.append(RecipeStep(text=change.replacement))
                elif change.field == RecipeReviewField.note:
                    index = self._require_index(change.index, updated.notes, change.field)
                    note = updated.notes[index]
                    self._require_current(note.text, change.original)
                    updated.notes[index] = RecipeNote(title=note.title, text=change.replacement)
                elif change.field in {
                    RecipeReviewField.prep_time,
                    RecipeReviewField.cook_time,
                    RecipeReviewField.total_time,
                    RecipeReviewField.recipe_yield,
                }:
                    current = getattr(updated, change.field.value)
                    self._require_current(current, change.original)
                    setattr(updated, change.field.value, change.replacement)

        return updated
