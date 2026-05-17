from pydantic import BaseModel, ConfigDict


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    budget_id: str
    category_group_id: str | None
    name: str
    hidden: bool
