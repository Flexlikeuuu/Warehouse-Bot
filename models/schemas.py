from typing import Optional, List
from pydantic import BaseModel, Field


class CatalogPosition(BaseModel):
    row_idx: int = Field(..., description="1-based row index in spreadsheet")
    section: str = Field(default="", description="Section name, e.g. 'ОВ 3' or 'ЭМ3'")
    item_num: Optional[str] = Field(default=None, description="Specification number or ID")
    name: str = Field(..., description="Full technical name from specification")
    unit: str = Field(..., description="Unit of measurement: м, шт, кг, etc.")
    plan_qty: float = Field(default=0.0, description="Estimated total volume (к-во)")
    price_per_unit: float = Field(default=0.0, description="Price per unit (ЗП за ед.)")
    total_price: float = Field(default=0.0, description="Total cost (ЗП на руки итого)")
    completed_qty: float = Field(default=0.0, description="Total completed volume to date")
    remaining_qty: float = Field(default=0.0, description="Remaining volume to complete")
    aliases: List[str] = Field(default_factory=list, description="Common colloquial aliases / slang")

    def display_name(self, max_length: int = 60) -> str:
        s = self.name if len(self.name) <= max_length else self.name[:max_length-3] + "..."
        return f"[{self.section}] #{self.item_num or self.row_idx} {s} ({self.unit})"


class ReportItem(BaseModel):
    position: CatalogPosition
    volume: float = Field(..., description="Reported volume for the day")
    unit: str = Field(..., description="Unit of measurement used by master")
    raw_text: str = Field(default="", description="Snippet from master's message")
    is_over_limit: bool = Field(default=False, description="True if volume > remaining_qty")
    over_limit_amount: float = Field(default=0.0)
    warning_msg: Optional[str] = None


class AmbiguousCandidate(BaseModel):
    row_idx: int
    name: str
    section: str
    unit: str
    remaining_qty: float


class AmbiguousItem(BaseModel):
    raw_text: str
    volume: float
    unit: str
    candidates: List[AmbiguousCandidate] = Field(default_factory=list)
    reason: str = Field(default="Подходит несколько позиций спецификации")


class UnrecognizedItem(BaseModel):
    raw_text: str
    volume: Optional[float] = None
    unit: Optional[str] = None
    reason: str = "Позиция не найдена в спецификации"


class ExtractionResult(BaseModel):
    is_question: bool = False
    question_query: Optional[str] = None
    target_row_idx: Optional[int] = None
    matched_items: List[ReportItem] = Field(default_factory=list)
    ambiguous_items: List[AmbiguousItem] = Field(default_factory=list)
    unrecognized_items: List[UnrecognizedItem] = Field(default_factory=list)
    raw_input: str = ""

