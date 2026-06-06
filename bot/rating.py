"""
SMV-ранговая система. Ранг = winrate (лайки / всего оценок).
До MIN_VOTES — калибровка, ранг скрыт.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    slug:   str
    emoji:  str
    min_wr: float


MIN_VOTES = 50

TIERS = [
    Tier("chad",     "👁️‍🗨️", 0.95),
    Tier("chadlite", "🔪",   0.80),
    Tier("htn",      "🔮",   0.60),
    Tier("mtn",      "🍄",   0.45),
    Tier("ltn",      "🦴",   0.30),
    Tier("sub5",     "🧱",   0.15),
    Tier("sub3",     "🕳️",  0.00),
]


def get_tier(winrate: float) -> Tier:
    for tier in TIERS:
        if winrate >= tier.min_wr:
            return tier
    return TIERS[-1]


def rating_bar(winrate: float, width: int = 8) -> str:
    filled = round(winrate * width)
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def format_rating_line(avg_rating: float, rating_count: int) -> str:
    """
    До 50 оценок:  🧬 <i>Калибровка · 12/50</i>
    После:         📊 [██████░░] 78% 🔮 htn
    """
    if rating_count < MIN_VOTES:
        return f"🧬 <i>Калибровка · {rating_count}/{MIN_VOTES}</i>"

    pct  = round(avg_rating * 100)
    tier = get_tier(avg_rating)
    bar  = rating_bar(avg_rating)
    return f"📊 <code>{bar}</code> <b>{pct}%</b> {tier.emoji} <b>{tier.slug}</b>"
