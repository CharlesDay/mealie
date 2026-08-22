<template>
  <div class="d-flex flex-wrap ga-2 px-4 pt-3 d-print-none">
    <v-btn
      v-if="group?.aiProviderSettings?.aiEnabled"
      color="primary"
      variant="tonal"
      :prepend-icon="$globals.icons.autoFix"
      @click="openReview"
    >
      Improve recipe
    </v-btn>
    <v-btn variant="tonal" :prepend-icon="$globals.icons.timelineText" @click="openHistory">
      Version history
    </v-btn>
  </div>

  <BaseDialog
    v-model="restoreDialog"
    title="Restore this recipe version?"
    color="warning"
    :icon="$globals.icons.alertCircle"
    can-confirm
    @confirm="confirmRestore"
  >
    <v-card-text>The current recipe will be saved as another revision before this version is restored.</v-card-text>
  </BaseDialog>

  <v-dialog v-model="reviewDialog" max-width="900" scrollable>
    <v-card>
      <v-card-title>AI recipe review</v-card-title>
      <v-card-subtitle>Suggestions are never saved until you select and apply them.</v-card-subtitle>
      <v-card-text>
        <v-textarea
          v-model="goal"
          label="What should the review focus on?"
          rows="2"
          auto-grow
          :disabled="reviewLoading"
        />
        <v-btn color="primary" :loading="reviewLoading" class="mb-4" @click="runReview">
          Review recipe
        </v-btn>

        <v-alert v-if="review" type="info" variant="tonal" class="mb-3">
          {{ review.summary }}
        </v-alert>
        <v-card
          v-for="(suggestion, index) in review?.suggestions || []"
          :key="`${suggestion.title}-${index}`"
          variant="outlined"
          class="mb-3"
        >
          <v-card-title class="d-flex align-center ga-2">
            <v-checkbox-btn v-model="selectedSuggestions" :value="index" />
            <span>{{ suggestion.title }}</span>
            <v-chip size="small">
              {{ suggestion.category }}
            </v-chip>
          </v-card-title>
          <v-card-text>
            <p class="mb-2">
              {{ suggestion.rationale }}
            </p>
            <div v-for="(change, changeIndex) in suggestion.changes" :key="changeIndex" class="mb-2">
              <div class="text-caption text-medium-emphasis">
                {{ change.field.replaceAll("_", " ") }}
              </div>
              <div v-if="change.original" class="text-error text-decoration-line-through">
                {{ change.original }}
              </div>
              <div class="text-success">
                {{ change.replacement }}
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="reviewDialog = false">
          Close
        </v-btn>
        <v-btn
          color="success"
          :disabled="selectedSuggestions.length === 0"
          :loading="applyLoading"
          @click="applySelected"
        >
          Apply selected
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="historyDialog" max-width="780" scrollable>
    <v-card>
      <v-card-title>Recipe version history</v-card-title>
      <v-card-subtitle>The latest 50 saved versions are retained.</v-card-subtitle>
      <v-card-text>
        <v-progress-linear v-if="historyLoading" indeterminate />
        <v-alert v-else-if="revisions.length === 0" type="info" variant="tonal">
          A revision will appear after the next recipe edit.
        </v-alert>
        <v-list v-else lines="three">
          <v-list-item v-for="revision in revisions" :key="revision.id">
            <v-list-item-title>{{ formatDate(revision.createdAt) }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ sourceLabel(revision.source) }}
              <span v-if="changedFields(revision).length"> · {{ changedFields(revision).join(", ") }}</span>
            </v-list-item-subtitle>
            <template #append>
              <v-btn color="warning" variant="text" :loading="restoringId === revision.id" @click="restore(revision)">
                Restore
              </v-btn>
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="historyDialog = false">
          Close
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { Recipe } from "~/lib/api/types/recipe";
import type { RecipeRevision, RecipeReviewResponse } from "~/lib/api/types/recipe-coach";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import { useGroupSelf } from "~/composables/use-groups";

const props = defineProps<{ recipe: Recipe }>();
const emit = defineEmits<{ updated: [recipe: Recipe] }>();
const api = useUserApi();
const { group } = useGroupSelf();

const reviewDialog = ref(false);
const historyDialog = ref(false);
const reviewLoading = ref(false);
const applyLoading = ref(false);
const historyLoading = ref(false);
const restoringId = ref<string | null>(null);
const restoreDialog = ref(false);
const pendingRestore = ref<RecipeRevision | null>(null);
const goal = ref("Improve flavor, clarity, consistency, and reliability");
const review = ref<RecipeReviewResponse | null>(null);
const selectedSuggestions = ref<number[]>([]);
const revisions = ref<RecipeRevision[]>([]);

function openReview() {
  reviewDialog.value = true;
}

async function runReview() {
  reviewLoading.value = true;
  selectedSuggestions.value = [];
  const { data, error } = await api.recipes.review(props.recipe.slug, goal.value);
  reviewLoading.value = false;
  if (error || !data) {
    alert.error("The AI review could not be completed.");
    return;
  }
  review.value = data;
}

async function applySelected() {
  if (!review.value) return;
  const suggestions = review.value.suggestions.filter((_, index) => selectedSuggestions.value.includes(index));
  applyLoading.value = true;
  const { data, error } = await api.recipes.applyReview(props.recipe.slug, suggestions);
  applyLoading.value = false;
  if (error || !data) {
    alert.error("The selected suggestions could not be applied. Run the review again if the recipe changed.");
    return;
  }
  emit("updated", data);
  alert.success("Recipe improvements applied. The previous version is available in history.");
  reviewDialog.value = false;
}

async function openHistory() {
  historyDialog.value = true;
  historyLoading.value = true;
  const { data, error } = await api.recipes.getRevisions(props.recipe.slug);
  historyLoading.value = false;
  if (error || !data) {
    alert.error("Recipe history could not be loaded.");
    return;
  }
  revisions.value = data;
}

function restore(revision: RecipeRevision) {
  pendingRestore.value = revision;
  restoreDialog.value = true;
}

async function confirmRestore() {
  const revision = pendingRestore.value;
  if (!revision) return;
  restoringId.value = revision.id;
  const { data, error } = await api.recipes.restoreRevision(props.recipe.slug, revision.id);
  restoringId.value = null;
  if (error || !data) {
    alert.error("That recipe version could not be restored.");
    return;
  }
  pendingRestore.value = null;
  emit("updated", data);
  alert.success("Recipe version restored. The version you replaced was also saved.");
  await openHistory();
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function sourceLabel(source: string) {
  return source === "ai-review" ? "AI review" : source === "restore" ? "Restored version" : "Manual edit";
}

function changedFields(revision: RecipeRevision) {
  const labels: Array<[keyof Recipe, string]> = [
    ["description", "description"],
    ["recipeIngredient", "ingredients"],
    ["recipeInstructions", "instructions"],
    ["notes", "notes"],
    ["prepTime", "prep time"],
    ["cookTime", "cook time"],
    ["totalTime", "total time"],
    ["recipeYield", "yield"],
  ];
  return labels
    .filter(([key]) => JSON.stringify(revision.snapshot[key]) !== JSON.stringify(props.recipe[key]))
    .map(([, label]) => label);
}
</script>
