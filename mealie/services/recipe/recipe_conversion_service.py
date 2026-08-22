import re
from dataclasses import dataclass

from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_conversion import RecipeConversionResponse, RecipeUnitSystem
from mealie.schema.recipe.recipe_ingredient import CreateIngredientUnit, RecipeIngredient, StandardizedUnitType
from mealie.schema.response.pagination import PaginationQuery

from .recipe_service import RecipeServiceBase


@dataclass(frozen=True)
class DensityRule:
    pattern: re.Pattern[str]
    grams_per_milliliter: float


DENSITY_RULES = [
    DensityRule(re.compile(r"\b(?:(?:all-purpose|plain|bread|cake|pastry|whole[ -]?wheat)\s+)?flour\b", re.I), 0.5),
    DensityRule(re.compile(r"\b(?:powdered sugar|icing sugar|confectioners?' sugar)\b", re.I), 0.5),
    DensityRule(re.compile(r"\bbrown sugar\b", re.I), 0.92),
    DensityRule(re.compile(r"\b(?:(?:granulated|caster|white)\s+)?sugar\b", re.I), 0.83),
    DensityRule(re.compile(r"\bbutter\b", re.I), 0.95),
    DensityRule(re.compile(r"\b(?:(?:olive|vegetable|canola|coconut)\s+)?oil\b", re.I), 0.92),
    DensityRule(re.compile(r"\b(?:honey|molasses|(?:maple\s+)?syrup)\b", re.I), 1.4),
    DensityRule(re.compile(r"\b(?:milk|cream|yogurt|buttermilk)\b", re.I), 1.03),
]

TEMPERATURE_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:°\s*)?(Fahrenheit|Celsius|F|C)\b", re.I)


class RecipeConversionService(RecipeServiceBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        units = self.repos.ingredient_units.page_all(PaginationQuery(page=1, per_page=-1)).items
        self.units = {
            unit.standard_unit: unit
            for unit in units
            if unit.standard_unit and unit.standard_quantity == 1 and unit.standard_unit not in {None, ""}
        }

    @staticmethod
    def _density(ingredient: RecipeIngredient) -> tuple[float, bool]:
        context = " ".join(
            value for value in [ingredient.food.name if ingredient.food else "", ingredient.note or ""] if value
        )
        for rule in DENSITY_RULES:
            if rule.pattern.search(context):
                return rule.grams_per_milliliter, False
        return 1, True

    def _unit(self, standard_unit: StandardizedUnitType) -> CreateIngredientUnit:
        if match := self.units.get(standard_unit.value):
            return match
        return CreateIngredientUnit(
            name=standard_unit.value.replace("_", " "),
            standard_quantity=1,
            standard_unit=standard_unit,
        )

    @staticmethod
    def _metric_mass(grams: float) -> tuple[float, StandardizedUnitType]:
        if grams >= 1000:
            return round(grams / 1000, 2), StandardizedUnitType.KILOGRAM
        return (round(grams, 1) if grams < 10 else round(grams)), StandardizedUnitType.GRAM

    @staticmethod
    def _imperial_volume(milliliters: float) -> tuple[float, StandardizedUnitType]:
        if milliliters < 120:
            return round((milliliters / 29.5735) * 8) / 8, StandardizedUnitType.FLUID_OUNCE
        return round((milliliters / 240) * 8) / 8, StandardizedUnitType.CUP

    @staticmethod
    def _imperial_mass(grams: float) -> tuple[float, StandardizedUnitType]:
        if grams >= 453.592:
            return round(grams / 453.592, 2), StandardizedUnitType.POUND
        return round((grams / 28.3495) * 8) / 8, StandardizedUnitType.OUNCE

    def _convert_ingredient(
        self, ingredient: RecipeIngredient, target: RecipeUnitSystem
    ) -> tuple[RecipeIngredient, str | None]:
        converted = ingredient.model_copy(deep=True)
        if converted.quantity is None or not converted.unit:
            return converted, None
        standard_unit = converted.unit.standard_unit
        standard_quantity = converted.unit.standard_quantity
        if not standard_unit or not standard_quantity:
            return converted, None

        amount = converted.quantity * standard_quantity
        target_amount: float
        target_unit: StandardizedUnitType
        assumption: str | None = None
        if target == RecipeUnitSystem.metric:
            if standard_unit == StandardizedUnitType.CUP:
                density, assumed = self._density(converted)
                target_amount, target_unit = self._metric_mass(amount * 240 * density)
                if assumed:
                    name = converted.food.name if converted.food else converted.display
                    assumption = f"{name}: used the default 1 g/mL density"
            elif standard_unit == StandardizedUnitType.FLUID_OUNCE and standard_quantity >= 1:
                density, assumed = self._density(converted)
                target_amount, target_unit = self._metric_mass(amount * 29.5735 * density)
                if assumed:
                    name = converted.food.name if converted.food else converted.display
                    assumption = f"{name}: used the default 1 g/mL density"
            elif standard_unit == StandardizedUnitType.OUNCE:
                target_amount, target_unit = self._metric_mass(amount * 28.3495)
            elif standard_unit == StandardizedUnitType.POUND:
                target_amount, target_unit = self._metric_mass(amount * 453.592)
            else:
                return converted, None
        else:
            if standard_unit == StandardizedUnitType.MILLILITER:
                target_amount, target_unit = self._imperial_volume(amount)
            elif standard_unit == StandardizedUnitType.LITER:
                target_amount, target_unit = self._imperial_volume(amount * 1000)
            elif standard_unit == StandardizedUnitType.GRAM:
                target_amount, target_unit = self._imperial_mass(amount)
            elif standard_unit == StandardizedUnitType.KILOGRAM:
                target_amount, target_unit = self._imperial_mass(amount * 1000)
            else:
                return converted, None

        converted.quantity = target_amount
        converted.unit = self._unit(target_unit)
        converted.display = ""
        converted.original_text = None
        return converted, assumption

    @staticmethod
    def _convert_temperatures(text: str | None, target: RecipeUnitSystem) -> tuple[str | None, int]:
        if not text:
            return text, 0
        count = 0

        def replacement(match: re.Match[str]) -> str:
            nonlocal count
            amount = float(match.group(1))
            source = RecipeUnitSystem.imperial if match.group(2).lower().startswith("f") else RecipeUnitSystem.metric
            if source == target:
                return match.group(0)
            count += 1
            converted = (
                round((amount - 32) * 5 / 9) if target == RecipeUnitSystem.metric else round(amount * 9 / 5 + 32)
            )
            return f"{converted}°{'C' if target == RecipeUnitSystem.metric else 'F'}"

        return TEMPERATURE_PATTERN.sub(replacement, text), count

    def convert(self, recipe: Recipe, target: RecipeUnitSystem) -> RecipeConversionResponse:
        converted = recipe.model_copy(deep=True)
        conversions = 0
        assumptions: list[str] = []
        ingredients: list[RecipeIngredient] = []
        for ingredient in converted.recipe_ingredient or []:
            converted_ingredient, assumption = self._convert_ingredient(ingredient, target)
            if converted_ingredient.quantity != ingredient.quantity or converted_ingredient.unit != ingredient.unit:
                conversions += 1
            if assumption:
                assumptions.append(assumption)
            converted_ingredient.note, temperature_count = self._convert_temperatures(converted_ingredient.note, target)
            conversions += temperature_count
            ingredients.append(converted_ingredient)
        converted.recipe_ingredient = ingredients

        converted.description, count = self._convert_temperatures(converted.description, target)
        conversions += count
        for instruction in converted.recipe_instructions or []:
            instruction.text, count = self._convert_temperatures(instruction.text, target)
            conversions += count
        for note in converted.notes or []:
            note.text, count = self._convert_temperatures(note.text, target)
            conversions += count

        return RecipeConversionResponse(
            recipe=converted,
            conversions=conversions,
            assumptions=assumptions,
        )
