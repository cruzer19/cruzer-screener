import feedparser

from urllib.parse import quote_plus
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ==========================================================
# CONFIG
# ==========================================================

MAX_NEWS_AGE_DAYS = 3

# ==========================================================
# KEYWORDS
# ==========================================================

NEGATIVE_KEYWORDS = {

    "turun": 1,
    "jatuh": 2,
    "anjlok": 2,
    "merosot": 2,
    "ambles": 2,
    "terkoreksi": 1,
    "melemah": 1,

    "jual": 1,
    "dijual": 2,
    "penjualan": 2,
    "aksi jual": 2,
    "tekanan jual": 2,

    "crossing": 2,
    "crossing besar": 3,

    "dihajar": 2,
    "dibuang": 2,
    "dilepas": 2,
    "distribusi": 2,

    "jual asing": 2,
    "asing jual": 2,

    "beban ihsg": 2,
    "terpuruk": 2,
    "lesu": 1,
    "rawan koreksi": 1,

    "rugi": 2,
    "merugi": 2,
    "utang": 2,
    "gagal bayar": 3,
    "kasus": 2,
    "gugat": 2,

    "suspend": 5,
    "suspensi": 5,
    "delisting": 5,
    "fraud": 5,
    "pailit": 5,
    "bangkrut": 5,
    "pidana": 5
}

POSITIVE_KEYWORDS = {

    "naik": 1,
    "menguat": 1,
    "rebound": 1,
    "reli": 1,

    "laba": 1,
    "catat laba": 2,
    "bukukan laba": 2,
    "tumbuh": 1,
    "kinerja solid": 2,

    "diborong": 2,
    "dikoleksi": 2,
    "akumulasi": 2,
    "kumpulkan": 2,

    "asing": 1,
    "asing beli": 2,
    "net buy asing": 2,

    "unggulan": 1,
    "prospektif": 1,
    "menarik": 1,
    "target harga": 1,
    "potensi naik": 1,
    "rekomendasi beli": 2,
    "optimistis": 1,

    "akuisisi": 2,
    "ekspansi": 1,
    "dividen": 2,
    "dividen jumbo": 3,
    "buyback": 2
}

HIGH_RISK_KEYWORDS = [

    "suspend",
    "suspensi",
    "delisting",
    "fraud",
    "pailit",
    "bangkrut",
    "pidana"
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

# ==========================================================
# HELPER
# ==========================================================

def safe_parse_date(date_str):

    try:

        return parsedate_to_datetime(date_str)

    except:

        return None


def calculate_news_age_days(dt):

    if not dt:
        return None

    now = datetime.now(timezone.utc)

    return (
        now - dt.astimezone(timezone.utc)
    ).days


# ==========================================================
# MAIN FUNCTION
# ==========================================================

def fetch_stock_news(
    ticker,
    limit=5
):

    query = quote_plus(
        f"{ticker} saham"
    )

    url = (
        "https://news.google.com/rss/search"
        f"?q={query}"
        "&hl=id"
        "&gl=ID"
        "&ceid=ID:id"
    )

    feed = feedparser.parse(url)

    news = []

    score = 0

    high_risk = False
    speculative = False

    used_titles = set()

    # ======================================================
    # LOOP NEWS
    # ======================================================

    for entry in feed.entries:

        title_raw = getattr(
            entry,
            "title",
            ""
        ).strip()

        if not title_raw:
            continue

        title = title_raw.lower()

        # ==================================================
        # REMOVE DUPLICATE
        # ==================================================

        normalized_title = (

            title
            .replace("-", " ")
            .replace("|", " ")
            .replace("  ", " ")
            .strip()

        )

        if normalized_title in used_titles:
            continue

        used_titles.add(
            normalized_title
        )

        # ==================================================
        # DATE FILTER
        # ==================================================

        published_dt = safe_parse_date(
            getattr(
                entry,
                "published",
                ""
            )
        )

        age_days = calculate_news_age_days(
            published_dt
        )

        # skip berita lama
        if (
            age_days is not None
            and age_days > MAX_NEWS_AGE_DAYS
        ):
            continue

        # ==================================================
        # HIGH RISK
        # ==================================================

        for w in HIGH_RISK_KEYWORDS:

            if w in title:

                high_risk = True
                score -= 5

        # ==================================================
        # SPECULATIVE
        # ==================================================

        for w in SPECULATIVE_KEYWORDS:

            if w in title:

                speculative = True

        # ==================================================
        # NEGATIVE SCORE
        # ==================================================

        for w, weight in NEGATIVE_KEYWORDS.items():

            if w in title:

                score -= weight

        # ==================================================
        # POSITIVE SCORE
        # ==================================================

        for w, weight in POSITIVE_KEYWORDS.items():

            if w in title:

                score += weight

        # ==================================================
        # LINK
        # ==================================================

        link = None

        if (
            hasattr(entry, "link")
            and entry.link
        ):

            link = entry.link

        elif (
            hasattr(entry, "links")
            and len(entry.links) > 0
        ):

            link = entry.links[0].get(
                "href"
            )

        # ==================================================
        # SAVE NEWS
        # ==================================================

        news.append({

            "title": title_raw,

            "link": link,

            "published": getattr(
                entry,
                "published",
                ""
            ),

            "age_days": age_days
        })

        # limit
        if len(news) >= limit:
            break

    # ======================================================
    # NO RECENT NEWS
    # ======================================================

    if len(news) == 0:

        return {

            "score": 0,

            "sentiment": "NO_RECENT_NEWS",

            "high_risk": False,

            "speculative": False,

            "news_count": 0,

            "message": (
                f"Tidak ada berita terkait "
                f"{ticker} dalam "
                f"{MAX_NEWS_AGE_DAYS} hari terakhir"
            ),

            "news": []
        }

    # ======================================================
    # FINAL SENTIMENT
    # ======================================================

    if high_risk and speculative:

        sentiment = "SPECULATIVE"

    elif score <= -3:

        sentiment = "NEGATIVE"

    elif score >= 2:

        sentiment = "POSITIVE"

    else:

        sentiment = "NEUTRAL"

    # ======================================================
    # RETURN
    # ======================================================

    return {

        "score": score,

        "sentiment": sentiment,

        "high_risk": high_risk,

        "speculative": speculative,

        "news_count": len(news),

        "message": (
            f"Ditemukan "
            f"{len(news)} berita "
            f"dalam "
            f"{MAX_NEWS_AGE_DAYS} hari terakhir"
        ),

        "news": news
    }