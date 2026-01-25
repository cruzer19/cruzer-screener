from dataclasses import dataclass
from typing import List
from typing import Dict

class StockResult:
    score_breakdown: Dict[str, int]

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