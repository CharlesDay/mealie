from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, orm
from sqlalchemy.orm import Mapped, mapped_column

from mealie.db.models._model_base import BaseMixins, SqlAlchemyBase
from mealie.db.models._model_utils.auto_init import auto_init
from mealie.db.models._model_utils.guid import GUID

if TYPE_CHECKING:
    from ..users import User
    from .recipe import RecipeModel


class RecipeRevision(SqlAlchemyBase, BaseMixins):
    __tablename__ = "recipe_revisions"

    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    recipe_id: Mapped[GUID] = mapped_column(
        GUID, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("users.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    recipe: Mapped["RecipeModel"] = orm.relationship("RecipeModel", back_populates="revisions")
    user: Mapped["User"] = orm.relationship("User", foreign_keys=[user_id])

    @auto_init()
    def __init__(self, **_) -> None:
        pass
