import type { Recipe, RecipeIngredient } from "~/lib/api/types/recipe";
import type { RecipeUnitSystem } from "~/lib/api/types/recipe-conversion";

const metricUnits = new Set(["milliliter", "liter", "gram", "kilogram"]);
const imperialUnits = new Set(["fluid_ounce", "cup", "ounce", "pound"]);

export function detectRecipeUnitSystem(recipe: Recipe): RecipeUnitSystem | undefined {
  let metric = 0;
  let imperial = 0;
  const activeRecipes = new Set<string>();

  function countIngredients(ingredients: RecipeIngredient[], recipeKey: string) {
    if (activeRecipes.has(recipeKey)) return;
    activeRecipes.add(recipeKey);
    for (const ingredient of ingredients) {
      if (ingredient.referencedRecipe) {
        const linked = ingredient.referencedRecipe;
        countIngredients(linked.recipeIngredient || [], linked.id || linked.slug || linked.name);
      }
      const standardUnit = ingredient.unit?.standardUnit;
      if (standardUnit && metricUnits.has(standardUnit)) metric++;
      if (standardUnit && imperialUnits.has(standardUnit)) imperial++;
    }
    activeRecipes.delete(recipeKey);
  }

  countIngredients(recipe.recipeIngredient || [], recipe.id || recipe.slug);
  const text = [
    recipe.description,
    ...(recipe.recipeInstructions || []).map(instruction => instruction.text),
    ...(recipe.notes || []).map(note => note.text),
  ].join("\n");
  metric += [...text.matchAll(/\d\s*(?:°\s*)?(?:Celsius|C)\b/gi)].length;
  imperial += [...text.matchAll(/\d\s*(?:°\s*)?(?:Fahrenheit|F)\b/gi)].length;
  if (metric === imperial) return undefined;
  return metric > imperial ? "metric" : "imperial";
}
