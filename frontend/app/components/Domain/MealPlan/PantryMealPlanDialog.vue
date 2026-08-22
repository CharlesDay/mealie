<template>
  <v-dialog v-if="group?.aiProviderSettings?.aiEnabled" v-model="dialog" max-width="900" scrollable>
    <RecipeDialogAddToShoppingList
      v-if="shoppingLists"
      v-model="shoppingListDialog"
      :recipes="recipeForShoppingList ? [{ ...recipeForShoppingList, scale: 1 }] : []"
      :shopping-lists="shoppingLists"
    />
    <template #activator="{ props: activatorProps }">
      <v-btn color="primary" variant="tonal" :prepend-icon="$globals.icons.autoFix" v-bind="activatorProps">
        Plan from pantry
      </v-btn>
    </template>
    <v-card>
      <v-card-title>Plan meals from your pantry</v-card-title>
      <v-card-subtitle>Pantry matches are prioritized; recipes that need a shop remain visible.</v-card-subtitle>
      <v-card-text>
        <v-textarea v-model="preferences" label="Preferences for this plan" rows="2" auto-grow />
        <v-number-input
          v-model="maxMissingFoods"
          label="Prioritize recipes with up to this many missing ingredients"
          :min="0"
          :max="10"
        />
        <v-btn color="primary" :loading="loading" class="mb-4" @click="findRecipes">
          Find recipes
        </v-btn>

        <v-alert v-if="result" type="info" variant="tonal" class="mb-3">
          Mealie found {{ result.pantryFoods.length }} foods marked on hand. Review every suggestion before adding it.
        </v-alert>
        <v-alert v-if="result && result.suggestions.length === 0" type="warning" variant="tonal">
          No suitable recipes were found. Mark more foods as on hand or allow additional missing ingredients.
        </v-alert>
        <v-card
          v-for="(suggestion, index) in result?.suggestions || []"
          :key="`${suggestion.date}-${suggestion.recipe.id}`"
          variant="outlined"
          class="mb-3"
        >
          <v-card-title class="d-flex align-center ga-2">
            <v-checkbox-btn v-model="selected" :value="index" />
            <span>{{ suggestion.recipe.name }}</span>
          </v-card-title>
          <v-card-subtitle>{{ suggestion.date }} · {{ suggestion.entryType }}</v-card-subtitle>
          <v-card-text>
            <p>{{ suggestion.reason }}</p>
            <p v-if="suggestion.makeable" class="text-success mt-2">
              All linked ingredients are marked on hand.
            </p>
            <v-alert v-else type="warning" variant="tonal" density="compact" class="mt-2">
              <div>Not currently makeable.</div>
              <div v-if="suggestion.missingFoods.length">
                Missing: {{ suggestion.missingFoods.map(food => food.name).join(", ") }}
              </div>
              <div v-if="suggestion.unlinkedIngredientCount">
                {{ suggestion.unlinkedIngredientCount }} ingredient{{ suggestion.unlinkedIngredientCount === 1 ? " is" : "s are" }} not linked to a pantry food.
              </div>
            </v-alert>
            <v-btn
              v-if="!suggestion.makeable"
              variant="tonal"
              color="warning"
              size="small"
              class="mt-3"
              :loading="loadingShoppingLists"
              @click="addMissingToShoppingList(suggestion.recipe)"
            >
              Add missing ingredients to grocery list
            </v-btn>
          </v-card-text>
        </v-card>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="dialog = false">
          Close
        </v-btn>
        <v-btn color="success" :disabled="selected.length === 0" :loading="adding" @click="addSelected">
          Add selected to meal plan
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { format } from "date-fns";
import type { PantryPlanResponse } from "~/lib/api/types/recipe-coach";
import type { Recipe, RecipeSummary } from "~/lib/api/types/recipe";
import type { ShoppingListSummary } from "~/lib/api/types/household";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import { useGroupSelf } from "~/composables/use-groups";
import RecipeDialogAddToShoppingList from "~/components/Domain/Recipe/RecipeDialogAddToShoppingList.vue";

const props = defineProps<{ startDate: Date; days: number }>();
const emit = defineEmits<{ planned: [] }>();
const api = useUserApi();
const { group } = useGroupSelf();

const dialog = ref(false);
const loading = ref(false);
const adding = ref(false);
const preferences = ref("");
const maxMissingFoods = ref(3);
const result = ref<PantryPlanResponse | null>(null);
const selected = ref<number[]>([]);
const shoppingLists = ref<ShoppingListSummary[]>();
const shoppingListDialog = ref(false);
const loadingShoppingLists = ref(false);
const recipeForShoppingList = ref<Recipe | null>(null);

async function findRecipes() {
  loading.value = true;
  selected.value = [];
  const { data, error } = await api.mealplans.getPantrySuggestions({
    startDate: format(props.startDate, "yyyy-MM-dd"),
    days: Math.min(Math.max(props.days, 1), 14),
    maxMissingFoods: maxMissingFoods.value,
    preferences: preferences.value,
  });
  loading.value = false;
  if (error || !data) {
    alert.error("Pantry meal suggestions could not be generated.");
    return;
  }
  result.value = data;
  selected.value = data.suggestions.map((_, index) => index);
}

async function addMissingToShoppingList(recipe: RecipeSummary) {
  loadingShoppingLists.value = true;
  const { data } = await api.shopping.lists.getAll(1, -1, { orderBy: "name", orderDirection: "asc" });
  loadingShoppingLists.value = false;
  if (!data) {
    alert.error("Shopping lists could not be loaded.");
    return;
  }

  recipeForShoppingList.value = recipe as Recipe;
  shoppingLists.value = data.items as ShoppingListSummary[];
  shoppingListDialog.value = true;
}

async function addSelected() {
  if (!result.value) return;
  adding.value = true;
  let added = 0;
  for (const [index, suggestion] of result.value.suggestions.entries()) {
    if (!selected.value.includes(index) || !suggestion.recipe.id) continue;
    const { error } = await api.mealplans.createOne({
      date: suggestion.date,
      entryType: suggestion.entryType,
      recipeId: suggestion.recipe.id,
      title: "",
      text: "",
    });
    if (!error) added++;
  }
  adding.value = false;
  if (added === 0) {
    alert.error("No pantry suggestions were added.");
    return;
  }
  alert.success(`${added} pantry meal${added === 1 ? "" : "s"} added to the plan.`);
  emit("planned");
  dialog.value = false;
}
</script>
