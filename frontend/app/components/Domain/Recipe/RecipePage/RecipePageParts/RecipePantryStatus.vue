<template>
  <RecipeDialogAddToShoppingList
    v-model="shoppingListDialog"
    :recipes="[{ ...recipe, scale: 1 }]"
    :shopping-lists="shoppingLists"
    missing-structured-only
  />

  <v-card variant="tonal" class="mb-4 d-print-none">
    <v-card-title class="d-flex align-center ga-2 text-subtitle-1">
      <v-icon :color="missingFoods.length ? 'warning' : 'success'">
        {{ missingFoods.length ? $globals.icons.alertCircle : $globals.icons.checkboxMarkedCircle }}
      </v-icon>
      Pantry check
    </v-card-title>
    <v-card-text class="pt-0">
      <div v-if="structuredFoods.length" class="d-flex flex-wrap ga-2 mb-2">
        <v-chip color="success" size="small">
          {{ onHandFoods.length }} on hand
        </v-chip>
        <v-chip :color="missingFoods.length ? 'warning' : 'success'" size="small">
          {{ missingFoods.length }} missing
        </v-chip>
      </div>

      <p v-if="missingFoods.length" class="text-body-2">
        {{ missingFoods.map(food => food.name).join(", ") }}
      </p>
      <p v-else-if="structuredFoods.length" class="text-body-2 text-success">
        Every structured ingredient is marked on hand.
      </p>
      <p v-else class="text-body-2 text-medium-emphasis">
        Parse this recipe's ingredients into foods to compare them with your pantry.
      </p>

      <p v-if="unlinkedIngredientCount" class="text-caption text-medium-emphasis mt-2">
        {{ unlinkedIngredientCount }} unstructured ingredient{{ unlinkedIngredientCount === 1 ? "" : "s" }} could not be checked.
      </p>
    </v-card-text>
    <v-card-actions v-if="missingFoods.length">
      <v-btn
        color="warning"
        variant="tonal"
        :prepend-icon="$globals.icons.cartCheck"
        :loading="shoppingListsLoading"
        @click="openShoppingLists"
      >
        Add missing to shopping list
      </v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup lang="ts">
import RecipeDialogAddToShoppingList from "~/components/Domain/Recipe/RecipeDialogAddToShoppingList.vue";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import type { ShoppingListSummary } from "~/lib/api/types/household";
import type { Recipe } from "~/lib/api/types/recipe";
import { getRecipePantryStatus } from "~/lib/recipe/pantry-status";

const props = defineProps<{ recipe: Recipe }>();
const api = useUserApi();
const auth = useMealieAuth();

const shoppingListDialog = ref(false);
const shoppingListsLoading = ref(false);
const shoppingLists = ref<ShoppingListSummary[]>([]);
const currentHouseholdSlug = computed(() => auth.user.value?.householdSlug || "");

const pantryStatus = computed(() => getRecipePantryStatus(props.recipe, currentHouseholdSlug.value));

const structuredFoods = computed(() => pantryStatus.value.structuredFoods);
const onHandFoods = computed(() => pantryStatus.value.onHandFoods);
const missingFoods = computed(() => pantryStatus.value.missingFoods);
const unlinkedIngredientCount = computed(() => pantryStatus.value.unlinkedIngredientCount);

async function openShoppingLists() {
  shoppingListsLoading.value = true;
  const { data, error } = await api.shopping.lists.getAll(1, -1, { orderBy: "name", orderDirection: "asc" });
  shoppingListsLoading.value = false;
  if (error || !data) {
    alert.error("Shopping lists could not be loaded.");
    return;
  }

  shoppingLists.value = data.items || [];
  shoppingListDialog.value = true;
}
</script>
