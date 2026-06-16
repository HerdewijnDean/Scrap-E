from typing import Optional
from pydantic import BaseModel


class DTOMeasurement(BaseModel):
    device_id: int
    value_number: Optional[float] = None
    value_text: Optional[str] = None
    comment: Optional[str] = None


class DTOActuatorAction(BaseModel):
    device_id: int
    action_id: int
    value_number: Optional[float] = None
    value_text: Optional[str] = None
    comment: Optional[str] = None