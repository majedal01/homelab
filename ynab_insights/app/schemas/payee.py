from pydantic import BaseModel, ConfigDict


class PayeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    budget_id: str
    name: str
    transfer_account_id: str | None
