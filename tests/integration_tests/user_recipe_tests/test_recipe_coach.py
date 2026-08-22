from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_coach import PantryPlanAIChoice, PantryPlanAIResponse
from mealie.schema.recipe.recipe_ingredient import RecipeIngredient, SaveIngredientFood
from mealie.schema.recipe.recipe_settings import RecipeSettings
from mealie.services.openai import OpenAIService
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def test_pantry_plan_ai_schema_uses_plain_string_recipe_ids():
    schema = PantryPlanAIResponse.model_json_schema()
    recipe_id = schema["$defs"]["PantryPlanAIChoice"]["properties"]["recipe_id"]

    assert recipe_id["type"] == "string"
    assert "format" not in recipe_id


def test_recipe_revision_restore(api_client: TestClient, unique_user: TestUser):
    name = random_string(12)
    slug = api_client.post(api_routes.recipes, json={"name": name}, headers=unique_user.token).json()
    recipe_url = api_routes.recipes_slug(slug)

    recipe = api_client.get(recipe_url, headers=unique_user.token).json()
    original_description = recipe["description"]
    recipe["description"] = "Updated description"

    update = api_client.put(recipe_url, json=recipe, headers=unique_user.token)
    assert update.status_code == 200

    revisions = api_client.get(f"{recipe_url}/revisions", headers=unique_user.token)
    assert revisions.status_code == 200
    assert len(revisions.json()) == 1
    revision = revisions.json()[0]
    assert revision["source"] == "manual"
    assert revision["snapshot"]["description"] == original_description

    restore = api_client.post(
        f"{recipe_url}/revisions/{revision['id']}/restore",
        headers=unique_user.token,
    )
    assert restore.status_code == 200
    assert restore.json()["description"] == original_description

    updated_revisions = api_client.get(f"{recipe_url}/revisions", headers=unique_user.token).json()
    assert len(updated_revisions) == 2
    assert updated_revisions[0]["source"] == "restore"

    api_client.delete(recipe_url, headers=unique_user.token)


def test_apply_selected_recipe_review(api_client: TestClient, unique_user: TestUser):
    name = random_string(12)
    slug = api_client.post(api_routes.recipes, json={"name": name}, headers=unique_user.token).json()
    recipe_url = api_routes.recipes_slug(slug)
    recipe = api_client.get(recipe_url, headers=unique_user.token).json()

    response = api_client.post(
        f"{recipe_url}/review/apply",
        json={
            "suggestions": [
                {
                    "category": "clarity",
                    "title": "Clarify the description",
                    "rationale": "Make the expected result explicit.",
                    "changes": [
                        {
                            "field": "description",
                            "original": recipe["description"],
                            "replacement": "A clearer description",
                        }
                    ],
                }
            ]
        },
        headers=unique_user.token,
    )

    assert response.status_code == 200
    assert response.json()["description"] == "A clearer description"
    revisions = api_client.get(f"{recipe_url}/revisions", headers=unique_user.token).json()
    assert revisions[0]["source"] == "ai-review"

    api_client.delete(recipe_url, headers=unique_user.token)


def test_recipe_review_rejects_stale_changes(api_client: TestClient, unique_user: TestUser):
    slug = api_client.post(
        api_routes.recipes,
        json={"name": random_string(12)},
        headers=unique_user.token,
    ).json()
    recipe_url = api_routes.recipes_slug(slug)

    response = api_client.post(
        f"{recipe_url}/review/apply",
        json={
            "suggestions": [
                {
                    "category": "clarity",
                    "title": "Stale suggestion",
                    "rationale": "This suggestion was generated for older content.",
                    "changes": [
                        {
                            "field": "description",
                            "original": "No longer current",
                            "replacement": "Replacement",
                        }
                    ],
                }
            ]
        },
        headers=unique_user.token,
    )

    assert response.status_code == 409
    assert "changed after this AI review" in response.json()["detail"]["message"]
    api_client.delete(recipe_url, headers=unique_user.token)


def test_pantry_plan_recommendations_are_limited_to_candidates(
    api_client: TestClient,
    unique_user: TestUser,
    monkeypatch: MonkeyPatch,
):
    household = unique_user.repos.households.get_by_slug_or_id(unique_user.household_id)
    assert household
    food = unique_user.repos.ingredient_foods.create(
        SaveIngredientFood(
            id=uuid4(),
            name=random_string(10),
            group_id=unique_user.group_id,
            households_with_ingredient_food=[household.slug],
        )
    )
    recipe = unique_user.repos.recipes.create(
        Recipe(
            name=random_string(12),
            user_id=unique_user.user_id,
            group_id=unique_user.group_id,
            recipe_ingredient=[RecipeIngredient(food_id=food.id, food=food)],
            settings=RecipeSettings(),
        )
    )

    async def fake_response(*_, **__):
        return PantryPlanAIResponse(
            choices=[
                PantryPlanAIChoice(
                    recipe_id=str(recipe.id),
                    date=date(2026, 8, 22),
                    reason="Uses the food marked on hand.",
                ),
                PantryPlanAIChoice(
                    recipe_id=str(uuid4()),
                    date=date(2026, 8, 23),
                    reason="This hallucinated ID must be rejected.",
                ),
            ]
        )

    monkeypatch.setattr(OpenAIService, "get_response", fake_response)
    response = api_client.post(
        "/api/households/mealplans/pantry-suggestions",
        json={"startDate": "2026-08-22", "days": 2, "maxMissingFoods": 0, "preferences": ""},
        headers=unique_user.token,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["suggestions"]) == 1
    assert data["suggestions"][0]["recipe"]["id"] == str(recipe.id)
    assert data["suggestions"][0]["missingFoods"] == []

    unique_user.repos.recipes.delete(recipe.slug)
    unique_user.repos.ingredient_foods.delete(food.id)
