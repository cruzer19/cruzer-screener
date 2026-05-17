from typing import List

import asyncio

from concurrent.futures import ThreadPoolExecutor

from app.models.stock_result import StockResult
from app.screeners import SCREENER_MAP

# ======================================================
# CONFIG
# ======================================================

MAX_WORKERS = 11

MAX_CONCURRENT_TASKS = 11

MAX_RETRY = 3

RETRY_DELAY = 0.7

# ======================================================
# ENGINE
# ======================================================

class ScreenerEngine:

    """
    Stable Async Screener Engine

    Features:
    - parallel scanning
    - retry otomatis
    - semaphore limiter
    - anti random skip
    - stable untuk yfinance/API
    """

    def __init__(self):

        # thread pool
        self.executor = ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        )

        # limiter async
        self.semaphore = asyncio.Semaphore(
            MAX_CONCURRENT_TASKS
        )

    # ======================================================
    # ASYNC ANALYZE
    # ======================================================

    async def analyze_async(
        self,
        screener,
        kode: str
    ):

        async with self.semaphore:

            loop = asyncio.get_running_loop()

            for attempt in range(MAX_RETRY):

                try:

                    result = await loop.run_in_executor(
                        self.executor,
                        screener.analyze,
                        kode
                    )

                    return result

                except Exception as e:

                    print(
                        f"[RETRY {attempt+1}/{MAX_RETRY}] "
                        f"{kode}: {e}"
                    )

                    # kasih napas sedikit
                    await asyncio.sleep(RETRY_DELAY)

            print(f"[FAILED] {kode}")

            return None

    # ======================================================
    # ASYNC RUNNER
    # ======================================================

    async def run_async(
        self,
        saham_list: List[str],
        screener_type: str
    ) -> List[StockResult]:

        # ======================================================
        # VALIDATION
        # ======================================================

        if screener_type not in SCREENER_MAP:

            raise ValueError(
                f"Screener type '{screener_type}' "
                f"tidak ditemukan"
            )

        # ======================================================
        # INIT SCREENER
        # ======================================================

        screener_cls = SCREENER_MAP[
            screener_type
        ]

        screener = screener_cls()

        # ======================================================
        # CREATE TASKS
        # ======================================================

        tasks = [

            self.analyze_async(
                screener,
                kode
            )

            for kode in saham_list

        ]

        # ======================================================
        # RUN PARALLEL
        # ======================================================

        results = await asyncio.gather(
            *tasks,
            return_exceptions=False
        )

        # ======================================================
        # CLEAN RESULTS
        # ======================================================

        results = [

            r for r in results
            if r is not None

        ]

        # ======================================================
        # SORT
        # ======================================================

        results.sort(
            key=lambda x: x.score,
            reverse=True
        )

        # ======================================================
        # DEBUG
        # ======================================================

        print(
            f"\n✅ SUCCESS SCAN: "
            f"{len(results)} saham"
        )

        return results

    # ======================================================
    # PUBLIC RUN
    # ======================================================

    def run(
        self,
        saham_list: List[str],
        screener_type: str
    ) -> List[StockResult]:

        return asyncio.run(

            self.run_async(
                saham_list,
                screener_type
            )

        )