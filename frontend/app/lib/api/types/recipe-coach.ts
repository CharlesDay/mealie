import type { PlanEntryType } from "./meal-plan";
import type { IngredientFood, Recipe, RecipeSummary } from "./recipe";

export type RecipeReviewField
  = | "description"
    | "ingredient"
    | "new_ingredient"
    | "instruction"
    | "new_instruction"
    | "note"
    | "prep_time"
    | "cook_time"
    | "total_time"
    | "recipe_yield";

export interface RecipeReviewChange {
  field: RecipeReviewField;
  index?: number | null;
  original?: string | null;
  replacement: string;
}

export interface RecipeReviewSuggestion {
  category: string;
  title: string;
  rationale: string;
  changes: RecipeReviewChange[];
}

export interface RecipeReviewResponse {
  summary: string;
  suggestions: RecipeReviewSuggestion[];
}

export interface RecipeRevision {
  id: string;
  recipeId: string;
  userId: string;
  source: string;
  snapshot: Recipe;
  createdAt: string;
}

export interface PantryPlanRequest {
  startDate: string;
  days: number;
  maxMissingFoods: number;
  preferences: string;
}

export interface PantryPlanSuggestion {
  recipe: RecipeSummary;
  date: string;
  entryType: PlanEntryType;
  reason: string;
  missingFoods: IngredientFood[];
  unlinkedIngredientCount: number;
  makeable: boolean;
}

export interface PantryPlanResponse {
  pantryFoods: IngredientFood[];
  suggestions: PantryPlanSuggestion[];
}
