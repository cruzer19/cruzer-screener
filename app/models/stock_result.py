from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class StockResult:
    # ================= BASIC =================
    kode: str
    last_price: int
    score: int

    # ================= META =================
    setup: str
    trend: str

    # ================= ENTRY =================
    entry_low: int
    entry_high: int

    tp: List[int]
    sl: int
    rr: float

    # ================= INFO =================
    recommendation: str
    screener_type: str

    score_breakdown: Dict[str, int]

    # ================= RSI =================
    rsi_value: Optional[float] = None
    rsi_status: Optional[str] = None

    # ================= 🔥 NEW (RANKING) =================
    rank: float = 0