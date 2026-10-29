from pydantic import BaseModel, ConfigDict, Field


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: float = Field(ge=0, le=1_000_000_000)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=120)
    stock_quantity: int = Field(default=0, ge=0)
    product_type: str = Field(default="", max_length=80)


class ItemRead(ItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
