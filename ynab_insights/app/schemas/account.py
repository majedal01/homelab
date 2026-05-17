from pydantic import BaseModel, ConfigDict


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    budget_id: str
    name: str
    type: str
    balance_cents: int
    on_budget: bool
    closed: bool
