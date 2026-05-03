from dataclasses import dataclass, field
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

    # ================= 🔥 RANK =================
    rank: float = 0

    # ================= 🔥 NEW: PRICE STRUCTURE =================
    support: Optional[int] = None
    resistance: Optional[int] = None

    # ================= 🔥 NEW: SMART DATA =================
    accumulation_score: Optional[float] = None
    volume_score: Optional[float] = None

    # ================= 🔥 NEW: EXTENSIBLE (FUTURE PROOF) =================
    extra: Dict = field(default_factory=dict)