from app.core.engine import ScreenerEngine
from app.config.saham_list import SAHAM_LIST
from app.renderers.telegram import render_telegram

engine = ScreenerEngine(min_score=75)
results = engine.run(
    saham_list=SAHAM_LIST,
    screener_type="swing_2w"
)

message = render_telegram(results)
print(message)
