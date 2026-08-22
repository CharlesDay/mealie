from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_conversion import RecipeUnitSystem
from mealie.schema.recipe.recipe_ingredient import CreateIngredientFood, CreateIngredientUnit, RecipeIngredient
from mealie.schema.recipe.recipe_notes import RecipeNote
from mealie.schema.recipe.recipe_step import RecipeStep
from mealie.services.recipe.recipe_conversion_service import RecipeConversionService


def converter() -> RecipeConversionService:
    service = RecipeConversionService.__new__(RecipeConversionService)
    service.units = {}
    return service


def unit(name: str, standard_unit: str, standard_quantity: float = 1) -> CreateIngredientUnit:
    return CreateIngredientUnit(
        name=name,
        standard_unit=standard_unit,
        standard_quantity=standard_quantity,
    )


def test_convert_imperial_ingredients_to_density_aware_metric_weights():
    recipe = Recipe(
        name="Cake",
        recipe_ingredient=[
            RecipeIngredient(quantity=2, unit=unit("cup", "cup"), food=CreateIngredientFood(name="flour")),
            RecipeIngredient(quantity=2, unit=unit("cup", "cup"), food=CreateIngredientFood(name="water")),
            RecipeIngredient(quantity=1, unit=unit("tablespoon", "fluid_ounce", 0.5), food="vanilla"),
            RecipeIngredient(quantity=4, unit=unit("ounce", "ounce"), food="chocolate"),
        ],
        recipe_instructions=[RecipeStep(text="Bake at 350°F for 30 minutes.")],
        notes=[RecipeNote(title="Oven", text="Do not exceed 400 Fahrenheit.")],
    )

    response = converter().convert(recipe, RecipeUnitSystem.metric)

    assert [(item.quantity, item.unit.standard_unit) for item in response.recipe.recipe_ingredient] == [
        (240, "gram"),
        (480, "gram"),
        (1, "fluid_ounce"),
        (113, "gram"),
    ]
    assert response.recipe.recipe_instructions[0].text == "Bake at 177°C for 30 minutes."
    assert response.recipe.notes[0].text == "Do not exceed 204°C."
    assert response.conversions == 5
    assert len(response.assumptions) == 1
    assert "water" in response.assumptions[0]


def test_convert_metric_volume_and_mass_to_practical_imperial_units():
    recipe = Recipe(
        name="Bread",
        recipe_ingredient=[
            RecipeIngredient(quantity=240, unit=unit("milliliter", "milliliter"), food="milk"),
            RecipeIngredient(quantity=454, unit=unit("gram", "gram"), food="flour"),
            RecipeIngredient(quantity=5, unit=unit("gram", "gram"), food="salt"),
        ],
        description="Bake at 180 Celsius.",
    )

    response = converter().convert(recipe, RecipeUnitSystem.imperial)

    assert [(item.quantity, item.unit.standard_unit) for item in response.recipe.recipe_ingredient] == [
        (1, "cup"),
        (1.0, "pound"),
        (0.125, "ounce"),
    ]
    assert response.recipe.description == "Bake at 356°F."
    assert response.conversions == 4
    assert response.assumptions == []
