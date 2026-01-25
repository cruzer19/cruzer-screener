from typing import List
from app.models.stock_result import StockResult
from app.screeners import SCREENER_MAP


class ScreenerEngine:
    """
    Engine hanya bertugas:
    - menjalankan screener
    - mengumpulkan StockResult
    TIDAK melakukan filtering score (biar UI yang pegang kontrol)
    """

    def __init__(self):
        pass

    def run(self, saham_list: List[str], screener_type: str) -> List[StockResult]:
        if screener_type not in SCREENER_MAP:
            raise ValueError(f"Screener type '{screener_type}' tidak ditemukan")

        screener_cls = SCREENER_MAP[screener_type]
        screener = screener_cls()

        results: List[StockResult] = []

        for kode in saham_list:
            try:
                res = screener.analyze(kode)

                # skip jika tidak ada hasil
                if res is None:
                    continue

                results.append(res)

            except Exception as e:
                print(f"[ERROR] {kode}: {e}")

        # sort by score desc (biar rapi)
        results.sort(key=lambda x: x.score, reverse=True)
        return results