import json
from datetime import date, timedelta
from functools import cached_property

import sqlalchemy as sa
from dateutil.tz import tzlocal
from fastapi import APIRouter, Depends, HTTPException

from mealie.core.exceptions import mealie_registered_exceptions
from mealie.db.models.recipe.ingredient import IngredientFoodModel, households_to_ingredient_foods
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_meals import RepositoryMeals
from mealie.routes._base import controller
from mealie.routes._base.base_controllers import BaseCrudController
from mealie.routes._base.mixins import HttpRepo
from mealie.schema import mapper
from mealie.schema.meal_plan import CreatePlanEntry, ReadPlanEntry, SavePlanEntry, UpdatePlanEntry
from mealie.schema.meal_plan.new_meal import CreateRandomEntry, PlanEntryPagination, PlanEntryType
from mealie.schema.meal_plan.plan_rules import PlanRulesDay
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_coach import (
    PantryPlanAIResponse,
    PantryPlanRequest,
    PantryPlanResponse,
    PantryPlanSuggestion,
)
from mealie.schema.recipe.recipe_ingredient import IngredientFood
from mealie.schema.recipe.recipe_suggestion import RecipeSuggestionQuery, RecipeSuggestionResponseItem
from mealie.schema.response.pagination import PaginationQuery
from mealie.schema.response.responses import ErrorResponse
from mealie.services.event_bus_service.event_types import (
    EventMealplanData,
    EventOperation,
    EventTypes,
)
from mealie.services.openai import OpenAIService

router = APIRouter(prefix="/households/mealplans", tags=["Households: Mealplans"])


@controller(router)
class GroupMealplanController(BaseCrudController):
    @cached_property
    def repo(self) -> RepositoryMeals:
        return self.repos.meals

    def registered_exceptions(self, ex: type[Exception]) -> str:
        registered = {
            **mealie_registered_exceptions(self.translator),
        }
        return registered.get(ex, self.t("generic.server-error"))

    @cached_property
    def mixins(self):
        return HttpRepo[CreatePlanEntry, ReadPlanEntry, UpdatePlanEntry](
            self.repo,
            self.logger,
            self.registered_exceptions,
        )

    def _get_random_recipes_from_mealplan(
        self, plan_date: date, entry_type: PlanEntryType, limit: int = 1
    ) -> list[Recipe]:
        """
        Gets rules for a mealplan and returns a list of random recipes based on the rules.
        May return zero recipes if no recipes match the filter criteria.

        Recipes from all households are included unless the rules specify a household filter.
        """

        rules = self.repos.group_meal_plan_rules.get_rules(PlanRulesDay.from_date(plan_date), entry_type.value)
        cross_household_recipes = get_repositories(
            self.session, group_id=self.group_id, household_id=None
        ).recipes.by_user(self.user.id)

        qf_string = " AND ".join([f"({rule.query_filter_string})" for rule in rules if rule.query_filter_string])
        recipes_data = cross_household_recipes.page_all(
            pagination=PaginationQuery(
                page=1,
                per_page=limit,
                query_filter=qf_string,
                order_by="random",
                pagination_seed=self.repo._random_seed(),
            )
        )
        return recipes_data.items

    @router.get("", response_model=PlanEntryPagination)
    def get_all(
        self,
        q: PaginationQuery = Depends(PaginationQuery),
        start_date: date | None = None,
        end_date: date | None = None,
    ):
        # merge start and end dates into pagination query only if either is provided
        if start_date or end_date:
            if not start_date:
                date_filter = f"date <= {end_date}"

            elif not end_date:
                date_filter = f"date >= {start_date}"

            else:
                date_filter = f"date >= {start_date} AND date <= {end_date}"

            if q.query_filter:
                q.query_filter = f"({q.query_filter}) AND ({date_filter})"

            else:
                q.query_filter = date_filter

        return self.repo.page_all(pagination=q)

    @router.post("", response_model=ReadPlanEntry, status_code=201)
    def create_one(self, data: CreatePlanEntry):
        data = mapper.cast(data, SavePlanEntry, group_id=self.group_id, user_id=self.user.id)
        result = self.mixins.create_one(data)

        self.publish_event(
            event_type=EventTypes.mealplan_entry_created,
            document_data=EventMealplanData(
                operation=EventOperation.create,
                mealplan_id=result.id,
                recipe_id=data.recipe_id,
                recipe_name=result.recipe.name if result.recipe else None,
                recipe_slug=result.recipe.slug if result.recipe else None,
                date=data.date,
            ),
            group_id=result.group_id,
            household_id=result.household_id,
            message=f"Mealplan entry created for {data.date} for {data.entry_type}",
        )

        return result

    @router.get("/today")
    def get_todays_meals(self):
        local_tz = tzlocal()
        return self.repo.get_today(tz=local_tz)

    @router.post("/random", response_model=ReadPlanEntry)
    def create_random_meal(self, data: CreateRandomEntry):
        """
        `create_random_meal` is a route that provides the randomized functionality for mealplaners.
        It operates by following the rules set out in the household's mealplan settings. If no settings
        are set, it will return any random meal.

        Refer to the mealplan settings routes for more information on how rules can be applied
        to the random meal selector.
        """
        random_recipes = self._get_random_recipes_from_mealplan(data.date, data.entry_type)
        if not random_recipes:
            raise HTTPException(
                status_code=404, detail=ErrorResponse.respond(message=self.t("mealplan.no-recipes-match-your-rules"))
            )

        recipe = random_recipes[0]
        result = self.mixins.create_one(
            SavePlanEntry(
                date=data.date,
                entry_type=data.entry_type,
                recipe_id=recipe.id,
                group_id=self.group_id,
                user_id=self.user.id,
            )
        )

        self.publish_event(
            event_type=EventTypes.mealplan_entry_created,
            document_data=EventMealplanData(
                operation=EventOperation.create,
                mealplan_id=result.id,
                recipe_id=recipe.id,
                recipe_name=recipe.name,
                recipe_slug=recipe.slug,
                date=data.date,
            ),
            group_id=result.group_id,
            household_id=result.household_id,
            message=f"Mealplan entry created for {data.date} for {data.entry_type}",
        )

        return result

    @router.post("/pantry-suggestions", response_model=PantryPlanResponse)
    async def suggest_from_pantry(self, request: PantryPlanRequest) -> PantryPlanResponse:
        pantry_models = self.session.scalars(
            sa.select(IngredientFoodModel)
            .join(
                households_to_ingredient_foods,
                IngredientFoodModel.id == households_to_ingredient_foods.c.food_id,
            )
            .where(households_to_ingredient_foods.c.household_id == self.household_id)
            .order_by(IngredientFoodModel.name)
        ).all()
        pantry_foods = [IngredientFood.model_validate(food) for food in pantry_models]

        recipes = get_repositories(self.session, group_id=self.group_id, household_id=None).recipes.by_user(
            self.user.id
        )
        target_suggestion_count = max(5, request.days)
        candidates = recipes.find_suggested_recipes(
            RecipeSuggestionQuery(
                limit=min(max(request.days * 4, target_suggestion_count), 40),
                max_missing_foods=request.max_missing_foods,
                max_missing_tools=10,
                include_foods_on_hand=False,
                include_tools_on_hand=True,
            ),
            food_ids=[food.id for food in pantry_foods],
            require_food_match=False,
            prefer_food_matches=True,
        )
        all_recipes = recipes.get_all()
        recipe_details = {recipe.id: recipe for recipe in all_recipes}

        # Once the best pantry matches have been collected, fill the candidate
        # pool with the rest of the library. This guarantees useful meal ideas
        # even when pantry linking is incomplete or a recipe needs a full shop.
        candidate_ids = {candidate.recipe.id for candidate in candidates}
        for recipe in all_recipes:
            if recipe.id in candidate_ids:
                continue
            missing_foods: list[IngredientFood] = []
            seen_food_ids = {food.id for food in pantry_foods}
            for ingredient in recipe.recipe_ingredient:
                if not ingredient.food or ingredient.food.id in seen_food_ids:
                    continue
                seen_food_ids.add(ingredient.food.id)
                missing_foods.append(IngredientFood.model_validate(ingredient.food))
            candidates.append(
                RecipeSuggestionResponseItem(
                    recipe=recipe,
                    missing_foods=missing_foods,
                    missing_tools=[],
                )
            )

        if not candidates:
            return PantryPlanResponse(pantry_foods=pantry_foods, suggestions=[])

        dates = [request.start_date + timedelta(days=offset) for offset in range(request.days)]
        candidate_payload = [
            {
                "recipeId": str(item.recipe.id),
                "name": item.recipe.name,
                "missingFoods": [food.name for food in item.missing_foods],
                "categories": [category.name for category in item.recipe.recipe_category or []],
            }
            for item in candidates
        ]
        ai = OpenAIService(self.repos)
        response = await ai.get_response(
            ai.get_prompt("mealplans.plan-from-pantry"),
            json.dumps(
                {
                    "dates": [value.isoformat() for value in dates],
                    "preferences": request.preferences,
                    "pantryFoods": [food.name for food in pantry_foods],
                    "candidates": candidate_payload,
                }
            ),
            response_schema=PantryPlanAIResponse,
        )
        response = response or PantryPlanAIResponse(choices=[])

        by_id = {str(item.recipe.id): item for item in candidates}

        def unlinked_ingredient_count(candidate: RecipeSuggestionResponseItem) -> int:
            return sum(
                ingredient.food is None and ingredient.referenced_recipe is None
                for ingredient in recipe_details[candidate.recipe.id].recipe_ingredient
            )

        valid_dates = set(dates)
        seen_dates: set[date] = set()
        suggestions: list[PantryPlanSuggestion] = []
        for choice in response.choices:
            candidate = by_id.get(choice.recipe_id)
            if candidate is None or choice.date not in valid_dates or choice.date in seen_dates:
                continue
            seen_dates.add(choice.date)
            suggestions.append(
                PantryPlanSuggestion(
                    recipe=candidate.recipe,
                    date=choice.date,
                    entry_type=choice.entry_type,
                    reason=choice.reason,
                    missing_foods=candidate.missing_foods,
                    unlinked_ingredient_count=unlinked_ingredient_count(candidate),
                    makeable=not candidate.missing_foods and not unlinked_ingredient_count(candidate),
                )
            )

        # Models occasionally return only a few choices even when they have
        # suitable candidates for every requested date. Fill those omissions
        # from the already-ranked, server-filtered candidates so the planner
        # remains useful and never introduces an unvetted recipe.
        selected_recipe_ids = {str(item.recipe.id) for item in suggestions}
        remaining_candidates = [
            candidate for candidate in candidates if str(candidate.recipe.id) not in selected_recipe_ids
        ]
        fallback_candidates = remaining_candidates or candidates
        while len(suggestions) < target_suggestion_count:
            candidate = fallback_candidates[(len(suggestions) - len(selected_recipe_ids)) % len(fallback_candidates)]
            value = dates[len(suggestions) % len(dates)]
            suggestions.append(
                PantryPlanSuggestion(
                    recipe=candidate.recipe,
                    date=value,
                    entry_type=PlanEntryType.dinner,
                    reason="A top-ranked pantry match, selected to complete the plan.",
                    missing_foods=candidate.missing_foods,
                    unlinked_ingredient_count=unlinked_ingredient_count(candidate),
                    makeable=not candidate.missing_foods and not unlinked_ingredient_count(candidate),
                )
            )

        suggestions.sort(key=lambda item: item.date)
        return PantryPlanResponse(pantry_foods=pantry_foods, suggestions=suggestions)

    @router.get("/{item_id}", response_model=ReadPlanEntry)
    def get_one(self, item_id: int):
        return self.mixins.get_one(item_id)

    @router.put("/{item_id}", response_model=ReadPlanEntry)
    def update_one(self, item_id: int, data: UpdatePlanEntry):
        result = self.mixins.update_one(data, item_id)

        self.publish_event(
            event_type=EventTypes.mealplan_entry_updated,
            document_data=EventMealplanData(
                operation=EventOperation.update,
                mealplan_id=result.id,
                recipe_id=result.recipe_id,
                recipe_name=result.recipe.name if result.recipe else None,
                recipe_slug=result.recipe.slug if result.recipe else None,
                date=result.date,
            ),
            group_id=result.group_id,
            household_id=result.household_id,
            message=f"Mealplan entry updated for {result.date} for {result.entry_type}",
        )

        return result

    @router.delete("/{item_id}", response_model=ReadPlanEntry)
    def delete_one(self, item_id: int):
        result = self.mixins.delete_one(item_id)

        self.publish_event(
            event_type=EventTypes.mealplan_entry_deleted,
            document_data=EventMealplanData(
                operation=EventOperation.delete,
                mealplan_id=result.id,
                recipe_id=result.recipe_id,
                recipe_name=result.recipe.name if result.recipe else None,
                recipe_slug=result.recipe.slug if result.recipe else None,
                date=result.date,
            ),
            group_id=result.group_id,
            household_id=result.household_id,
            message=f"Mealplan entry deleted for {result.date} for {result.entry_type}",
        )

        return result
