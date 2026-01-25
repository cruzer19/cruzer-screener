from dataclasses import dataclass
from typing import List

@dataclass
class StockResult:
    kode: str
    last_price: int
    score: int
    setup: str
    trend: str
    entry_low: int
    entry_high: int
    tp: List[int]
    sl: int
    rr: float
    recommendation: str
    screener_type: str

    score_breakdown: Dict[str, int]