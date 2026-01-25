from app.screeners.swing_trade_week import SwingTradeWeekScreener
from app.screeners.swing_trade_day import SwingTradeDayScreener
from app.screeners.breakout import BreakoutScreener

SCREENER_MAP = {
    "swing_trade_week": SwingTradeWeekScreener,
    "swing_trade_day": SwingTradeDayScreener,
    "breakout": BreakoutScreener,
}