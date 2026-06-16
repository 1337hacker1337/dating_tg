"""bot/utils/geo.py — геоутилиты."""
import math
from typing import Optional

from bot import logger as log

_log = log.get(__name__)

_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
# из ответа Nominatim берём первое подходящее поле населённого пункта
_CITY_KEYS = ("city", "town", "village", "municipality", "county", "state")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в километрах."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


async def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """
    Координаты → название города. Вызывается ОДИН раз при сохранении локации,
    не на каждый показ карточки. При любой ошибке/таймауте → None (без города).
    """
    params = {
        "format": "jsonv2", "lat": f"{lat}", "lon": f"{lon}",
        "zoom": "10", "accept-language": "ru",
    }
    headers = {"User-Agent": "shroom-bot/1.0 (dating telegram bot)"}
    try:
        import aiohttp  # ленивый импорт — не нужен на горячем пути haversine
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(_NOMINATIM, params=params, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        address = (data or {}).get("address", {})
        for key in _CITY_KEYS:
            if address.get(key):
                return str(address[key])[:64]
    except Exception as e:
        _log.info("reverse_geocode failed: %s", e)
    return None
