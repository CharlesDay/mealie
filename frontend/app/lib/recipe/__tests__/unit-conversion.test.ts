import { describe, expect, test } from "vitest";
import type { Recipe } from "~/lib/api/types/recipe";
import { detectRecipeUnitSystem } from "~/lib/recipe/unit-conversion";

describe("detectRecipeUnitSystem", () => {
  test("detects structured metric and imperial units", () => {
    expect(detectRecipeUnitSystem({
      id: "metric",
      recipeIngredient: [{ quantity: 100, unit: { id: "g", name: "gram", standardUnit: "gram" } }],
    } as Recipe)).toBe("metric");
    expect(detectRecipeUnitSystem({
      id: "imperial",
      recipeIngredient: [{ quantity: 1, unit: { id: "cup", name: "cup", standardUnit: "cup" } }],
    } as Recipe)).toBe("imperial");
  });

  test("uses explicit cooking temperatures and reports mixed ties as unknown", () => {
    expect(detectRecipeUnitSystem({ id: "oven", recipeInstructions: [{ text: "Bake at 350°F." }] } as Recipe))
      .toBe("imperial");
    expect(detectRecipeUnitSystem({
      id: "mixed",
      recipeIngredient: [
        { quantity: 100, unit: { id: "g", name: "gram", standardUnit: "gram" } },
        { quantity: 1, unit: { id: "cup", name: "cup", standardUnit: "cup" } },
      ],
    } as Recipe)).toBeUndefined();
  });
});
