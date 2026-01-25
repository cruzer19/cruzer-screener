from abc import ABC, abstractmethod
from app.models.stock_result import StockResult

class BaseScreener(ABC):
    screener_type: str

    @abstractmethod
    def analyze(self, kode: str) -> StockResult | None:
        pass