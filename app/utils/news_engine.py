import feedparser
from urllib.parse import quote_plus

# =========================
# KEYWORDS + WEIGHT
# =========================

NEGATIVE_KEYWORDS = {
    # harga & performa
    "turun": 1,
    "jatuh": 2,
    "anjlok": 2,
    "merosot": 2,
    "ambles": 2,
    "terkoreksi": 1,

    # aksi pasar / distribusi
    "jual": 1,
    "dijual": 2,
    "penjualan": 2,
    "aksi jual": 2,
    "tekanan jual": 2,
    "crossing": 2,
    "crossing besar": 3,
    "beban ihsg": 2,

    # distribusi klasik
    "dihajar": 2,
    "dibuang": 2,
    "dilepas": 2,
    "jual asing": 2,
    "asing jual": 2,
    "distribusi": 2,

    # sentimen
    "lesu": 1,
    "melemah": 1,
    "terpuruk": 2,
    "rawan koreksi": 1,

    # fundamental / risiko
    "rugi": 2,
    "merugi": 2,
    "utang": 2,
    "gagal bayar": 3,
    "kasus": 2,
    "gugat": 2,

    # fatal
    "suspend": 5,
    "suspensi": 5,
    "delisting": 5,
    "fraud": 5,
    "pailit": 5,
    "bangkrut": 5,
    "pidana": 5
}

POSITIVE_KEYWORDS = {
    # harga & momentum
    "naik": 1,
    "menguat": 1,
    "rebound": 1,
    "reli": 1,

    # kinerja
    "laba": 1,
    "catat laba": 2,
    "bukukan laba": 2,
    "tumbuh": 1,
    "kinerja solid": 2,

    # institusi & akumulasi
    "diborong": 2,
    "dikoleksi": 2,
    "akumulasi": 2,
    "kumpulkan": 2,
    "asing": 1,
    "asing beli": 2,
    "net buy asing": 2,
    "investor institusi": 2,

    # outlook
    "unggulan": 1,
    "prospektif": 1,
    "menarik": 1,
    "target harga": 1,
    "potensi naik": 1,
    "rekomendasi beli": 2,

    # aksi korporasi
    "akuisisi": 2,
    "ekspansi": 1,
    "dividen": 2,
    "dividen jumbo": 3,
    "buyback": 2,
    "optimistis": 1
}

HIGH_RISK_KEYWORDS = [
    "suspend", "suspensi",
    "delisting", "fraud",
    "pailit", "bangkrut", "pidana"
]

SPECULATIVE_KEYWORDS = [
    "unsuspensi",
    "unsuspend",
    "lepas suspensi",
    "buka suspensi",
    "meroket",
    "melesat",
    "terbang",
    "auto reject atas",
    "ara",
    "saham panas",
    "rame ditransaksikan"
]

# =========================
# MAIN FUNCTION
# =========================

def fetch_stock_news(ticker, limit=5):
    query = quote_plus(f"{ticker} saham")
    url = f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"

    feed = feedparser.parse(url)

    news = []
    score = 0
    high_risk = False
    speculative = False

    for entry in feed.entries[:limit]:
        title = entry.title.lower()

        # -------------------------
        # HIGH RISK DETECTION
        # -------------------------
        for w in HIGH_RISK_KEYWORDS:
            if w in title:
                high_risk = True
                score -= 5

        # -------------------------
        # SPECULATIVE EVENT
        # -------------------------
        for w in SPECULATIVE_KEYWORDS:
            if w in title:
                speculative = True

        # -------------------------
        # NEGATIVE SCORING
        # -------------------------
        for w, weight in NEGATIVE_KEYWORDS.items():
            if w in title:
                score -= weight

        # -------------------------
        # POSITIVE SCORING
        # -------------------------
        for w, weight in POSITIVE_KEYWORDS.items():
            if w in title:
                score += weight

        # -------------------------
        # SAFE LINK EXTRACTION
        # -------------------------
        link = None
        if hasattr(entry, "link") and entry.link:
            link = entry.link
        elif hasattr(entry, "links") and len(entry.links) > 0:
            link = entry.links[0].get("href")

        news.append({
            "title": entry.title,
            "link": link,
            "published": getattr(entry, "published", "")
        })

    # =========================
    # FINAL SENTIMENT DECISION
    # =========================
    if high_risk and speculative:
        sentiment = "SPECULATIVE"
    elif score <= -3:
        sentiment = "NEGATIVE"
    elif score >= 2:
        sentiment = "POSITIVE"
    else:
        sentiment = "NEUTRAL"

    return {
        "score": score,
        "sentiment": sentiment,
        "high_risk": high_risk,
        "speculative": speculative,
        "news": news
    }