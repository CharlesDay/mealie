<template>
  <div class="d-flex justify-space-between align-center pt-2 pb-3">
    <RecipeScaleEditButton
      v-if="!isEditMode"
      v-model.number="scale"
      :recipe-servings="recipeServings"
      :edit-scale="hasFoodOrUnit && !isEditMode"
    />
    <v-btn-toggle
      :model-value="unitSystem"
      color="primary"
      variant="outlined"
      divided
      density="compact"
      @update:model-value="convertUnits"
    >
      <v-btn value="metric" size="small" :loading="loadingTarget === 'metric'">
        Metric
      </v-btn>
      <v-btn value="imperial" size="small" :loading="loadingTarget === 'imperial'">
        Imperial
      </v-btn>
    </v-btn-toggle>
  </div>
</template>

<script setup lang="ts">
import RecipeScaleEditButton from "~/components/Domain/Recipe/RecipeScaleEditButton.vue";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { Recipe } from "~/lib/api/types/recipe";
import { usePageState } from "~/composables/recipe-page/shared-state";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import type { RecipeUnitSystem } from "~/lib/api/types/recipe-conversion";
import { detectRecipeUnitSystem } from "~/lib/recipe/unit-conversion";

const props = defineProps<{ recipe: NoUndefinedField<Recipe> }>();

const scale = defineModel<number>({ default: 1 });
const emit = defineEmits<{ converted: [recipe: Recipe] }>();

const { isEditMode } = usePageState(props.recipe.slug);
const api = useUserApi();
const loadingTarget = ref<RecipeUnitSystem>();
const unitSystem = computed(() => detectRecipeUnitSystem(props.recipe));

async function convertUnits(target: RecipeUnitSystem | undefined) {
  if (!target || target === unitSystem.value || loadingTarget.value) return;
  loadingTarget.value = target;
  const { data, error } = await api.recipes.convertUnits(props.recipe.slug, props.recipe, target);
  loadingTarget.value = undefined;
  if (error || !data) {
    alert.error("Recipe units could not be converted.");
    return;
  }
  if (!data.conversions) {
    alert.info("No compatible measurements were found to convert.");
    return;
  }
  emit("converted", data.recipe);
  if (data.assumptions.length) {
    alert.warning(`${data.assumptions.length} conversion${data.assumptions.length === 1 ? " used" : "s used"} the default 1 g/mL density.`);
  }
  else {
    alert.success(`${data.conversions} measurement${data.conversions === 1 ? "" : "s"} converted to ${target}.`);
  }
}

const recipeServings = computed<number>(() => {
  return props.recipe.recipeServings || props.recipe.recipeYieldQuantity || 1;
});

const hasFoodOrUnit = computed(() => {
  if (props.recipe.recipeIngredient) {
    for (const ingredient of props.recipe.recipeIngredient) {
      if (ingredient.food || ingredient.unit) {
        return true;
      }
    }
  }
  return false;
});
</script>
