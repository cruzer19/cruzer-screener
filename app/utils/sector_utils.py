from app.config.saham_sector import SAHAM_SECTOR
from app.config.sector_badge import SECTOR_BADGE

def get_sector_badge(kode: str):
    sector = SAHAM_SECTOR.get(kode, "OTHER")
    emoji = SECTOR_BADGE.get(sector, "📦")
    return emoji, sector