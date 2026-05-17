from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    currency: str
    last_modified_on: datetime
