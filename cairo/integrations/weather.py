"""Current modelled weather and forecast from Open-Meteo, never LLM guesses."""

import json
import math
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlencode

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MAX_BYTES = 256000
TIMEOUT = 12
CODES = {
    0: "céu limpo",
    1: "predominantemente limpo",
    2: "parcialmente nublado",
    3: "nublado",
    45: "neblina",
    48: "neblina com geada",
    51: "garoa leve",
    53: "garoa",
    55: "garoa intensa",
    56: "garoa congelante",
    57: "garoa congelante intensa",
    61: "chuva leve",
    63: "chuva",
    65: "chuva forte",
    66: "chuva congelante",
    67: "chuva congelante forte",
    71: "neve leve",
    73: "neve",
    75: "neve forte",
    77: "grãos de neve",
    80: "pancadas leves",
    81: "pancadas de chuva",
    82: "pancadas fortes",
    85: "pancadas de neve",
    86: "pancadas fortes de neve",
    95: "trovoadas",
    96: "trovoadas com granizo",
    99: "trovoadas com granizo forte",
}


def get_json(url: str) -> dict:
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Cairo/0.4 (personal assistant)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Resposta do clima excedeu o limite")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Resposta do clima inválida")
            return result
    except (urllib.error.URLError, TimeoutError, OSError):
        raise OSError(
            "Não foi possível consultar Open-Meteo. Confira a internet e tente novamente."
        ) from None
    except (ValueError, UnicodeError):
        raise ValueError("O serviço do clima retornou dados inválidos") from None


def weather(city: str) -> dict:
    if not isinstance(city, str) or not 2 <= len(city.strip()) <= 120:
        raise ValueError("Informe a cidade, por exemplo: clima em Recife, Pernambuco")
    catalog = get_json(
        GEO_URL
        + "?"
        + urlencode(
            {"name": city.strip(), "count": 5, "language": "pt", "format": "json"}
        )
    )
    places = catalog.get("results", [])
    if not places:
        raise ValueError("Cidade não encontrada; informe cidade e estado ou país")
    if not isinstance(places, list):
        raise ValueError("Catálogo de cidades inválido")
    if not all(
        isinstance(place, dict) and isinstance(place.get("name"), str)
        for place in places
    ):
        raise ValueError("Catálogo de cidades inválido")
    # Never silently select one of several namesakes.
    if len(places) > 1:
        choices = [
            ", ".join(str(p[k]) for k in ("name", "admin1", "country") if p.get(k))
            for p in places
        ]
        return {
            "needs_location": True,
            "choices": choices,
            "message": "Encontrei mais de uma localização. Especifique cidade e estado/país:\n"
            + "\n".join(choices),
        }
    try:
        place = places[0]
        lat, lon = float(place["latitude"]), float(place["longitude"])
        if (
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            raise ValueError
        data = get_json(
            WEATHER_URL
            + "?"
            + urlencode(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "timezone": "auto",
                    "forecast_days": 2,
                    "temperature_unit": "celsius",
                    "wind_speed_unit": "kmh",
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                }
            )
        )
        current, daily = data["current"], data["daily"]
        for key in (
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "weather_code",
            "wind_speed_10m",
        ):
            if not isinstance(current[key], (int, float)) or not math.isfinite(
                current[key]
            ):
                raise ValueError
        location = ", ".join(
            str(place[k]) for k in ("name", "admin1", "country") if place.get(k)
        )
        condition = CODES.get(current["weather_code"], "condição não classificada")
        days = []
        for i, date in enumerate(daily["time"][:2]):
            values = [
                daily[k][i]
                for k in (
                    "temperature_2m_min",
                    "temperature_2m_max",
                    "precipitation_probability_max",
                )
            ]
            if not all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in values
            ):
                raise ValueError
            days.append(
                {
                    "date": date,
                    "min_c": values[0],
                    "max_c": values[1],
                    "rain_probability_percent": values[2],
                }
            )
        message = f"{location}: {current['temperature_2m']} °C, {condition}. Sensação de {current['apparent_temperature']} °C; umidade {current['relative_humidity_2m']}%; vento {current['wind_speed_10m']} km/h.\nAtualização: {current['time']} ({data['timezone']})."
        for day in days:
            message += f"\n{day['date']}: mínima {day['min_c']} °C, máxima {day['max_c']} °C; chance de chuva {day['rain_probability_percent']}%."
        message += "\nFonte: Open-Meteo (dados de modelos meteorológicos)."
        return {
            "location": location,
            "current": current,
            "forecast": days,
            "timezone": data["timezone"],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "source": "https://open-meteo.com/",
            "message": message,
        }
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        raise ValueError("O serviço do clima retornou dados incompletos") from None
