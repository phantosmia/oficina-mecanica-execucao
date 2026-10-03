from datetime import datetime

from pydantic import BaseModel, Field

from app.execution.domain.value_objects import JobStatus


class VehicleRead(BaseModel):
    plate: str
    brand: str | None = None
    model: str | None = None
    year: int | None = None


class DiagnosedItemRead(BaseModel):
    id: str
    name: str
    quantity: int
    unit_price: float
    subtotal: float


class DiagnosisRead(BaseModel):
    notes: str
    services: list[DiagnosedItemRead]
    parts: list[DiagnosedItemRead]
    labor_total: float
    parts_total: float
    total: float


class JobRead(BaseModel):
    order_id: int
    saga_id: str
    status: JobStatus
    status_since: datetime
    problem_description: str
    vehicle: VehicleRead | None
    diagnosis: DiagnosisRead | None
    repair_notes: str | None
    status_history: dict[str, datetime]


class ItemRequest(BaseModel):
    id: str
    quantity: int = Field(gt=0)


class DiagnosisRequest(BaseModel):
    notes: str = Field(min_length=1, description="O que o mecânico encontrou")
    services: list[ItemRequest] = Field(default_factory=list, max_length=50)
    parts: list[ItemRequest] = Field(default_factory=list, max_length=50)


class FinishRequest(BaseModel):
    notes: str | None = None
