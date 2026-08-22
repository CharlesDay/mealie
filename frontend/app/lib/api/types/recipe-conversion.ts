import type { Recipe } from "./recipe";

export type RecipeUnitSystem = "metric" | "imperial";

export interface RecipeConversionResponse {
  recipe: Recipe;
  conversions: number;
  assumptions: string[];
}
