#!/usr/bin/env python3
"""Fetch weather + official alerts into /opt/athan/web/weather.json (root cron, every 10 min).

Sources (free, no API key):
  Open-Meteo   https://open-meteo.com       current conditions, hourly rain chance, daily high/low
  NWS          https://api.weather.gov      official US watches/warnings/advisories for the point

Also derives simple household heads-ups: rain expected in the next 12 hours, freezing
or very hot temperatures today. Location comes from LATITUDE/LONGITUDE in /etc/default/athan.
"""
import json
import os
import re
import sys
import tempfile
import time
import urllib.request

CONF = "/etc/default/athan"
OUT = os.environ.get("WEATHER_OUT", "/opt/athan/web/weather.json")
UA = "athan-tv/1.0 (home prayer-times display)"   # NWS requires a User-Agent

# WMO weather codes -> (text, day icon, night icon)
WMO = {
    0: ("Clear", "☀️", "🌙"), 1: ("Mostly clear", "🌤️", "🌙"), 2: ("Partly cloudy", "⛅", "☁️"),
    3: ("Overcast", "☁️", "☁️"), 45: ("Fog", "🌫️", "🌫️"), 48: ("Freezing fog", "🌫️", "🌫️"),
    51: ("Light drizzle", "🌦️", "🌧️"), 53: ("Drizzle", "🌦️", "🌧️"), 55: ("Heavy drizzle", "🌧️", "🌧️"),
    56: ("Freezing drizzle", "🌧️", "🌧️"), 57: ("Freezing drizzle", "🌧️", "🌧️"),
    61: ("Light rain", "🌦️", "🌧️"), 63: ("Rain", "🌧️", "🌧️"), 65: ("Heavy rain", "🌧️", "🌧️"),
    66: ("Freezing rain", "🌧️", "🌧️"), 67: ("Freezing rain", "🌧️", "🌧️"),
    71: ("Light snow", "🌨️", "🌨️"), 73: ("Snow", "🌨️", "🌨️"), 75: ("Heavy snow", "❄️", "❄️"),
    77: ("Snow grains", "🌨️", "🌨️"), 80: ("Rain showers", "🌦️", "🌧️"), 81: ("Rain showers", "🌧️", "🌧️"),
    82: ("Heavy showers", "🌧️", "🌧️"), 85: ("Snow showers", "🌨️", "🌨️"), 86: ("Snow showers", "🌨️", "🌨️"),
    95: ("Thunderstorm", "⛈️", "⛈️"), 96: ("Thunderstorm, hail", "⛈️", "⛈️"), 99: ("Thunderstorm, hail", "⛈️", "⛈️"),
}
WET = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
RAIN_THRESHOLD = 50          # % chance that counts as "rain expected"
HOT_F, FREEZE_F = 90, 32


def read_conf(path):
    conf = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^\s*([A-Z_]+)=(.*)$', line)
                if m:
                    val = m.group(2).strip()
                    q = re.match(r'^(["\'])(.*?)\1', val)
                    conf[m.group(1)] = q.group(2) if q else val.split(" #", 1)[0].strip()
    except FileNotFoundError:
        pass
    return conf


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json, application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def hour_label(iso):                       # "2026-09-27T15:00" -> "3 PM"
    h = int(iso[11:13])
    return f"{h % 12 or 12} {'PM' if h >= 12 else 'AM'}"


def weather(lat, lon):
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
           "wind_speed_10m,precipitation,is_day"
           "&hourly=precipitation_probability,weather_code"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max"
           "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
           "&timezone=auto&forecast_days=2")
    w = get_json(url)
    c, h, d = w["current"], w["hourly"], w["daily"]
    code = int(c["weather_code"])
    text, day_icon, night_icon = WMO.get(code, ("", "🌡️", "🌡️"))
    cur = {
        "temp": round(c["temperature_2m"]), "feels": round(c["apparent_temperature"]),
        "humidity": round(c["relative_humidity_2m"]), "wind": round(c["wind_speed_10m"]),
        "code": code, "text": text, "icon": day_icon if c.get("is_day", 1) else night_icon,
    }
    today = {
        "high": round(d["temperature_2m_max"][0]), "low": round(d["temperature_2m_min"][0]),
        "rain_chance": d["precipitation_probability_max"][0], "uv": d["uv_index_max"][0],
    }

    notices = []
    now_hour = c["time"][:13]                                  # "YYYY-MM-DDTHH"
    if (c.get("precipitation") or 0) > 0 or code in WET:
        notices.append({"level": "info", "icon": "☔", "text": f"{text or 'Rain'} now — take an umbrella"})
    else:
        for t, p, hc in zip(h["time"], h["precipitation_probability"], h["weather_code"]):
            if t[:13] <= now_hour:
                continue
            if t[:13] > _plus_hours(now_hour, 12):
                break
            if p is not None and p >= RAIN_THRESHOLD:
                kind = "Thunderstorms" if hc in (95, 96, 99) else "Rain"
                notices.append({"level": "info", "icon": "🌧️", "text": f"{kind} likely around {hour_label(t)} ({p}%) — take an umbrella"})
                break
    if today["high"] >= HOT_F:
        notices.append({"level": "moderate", "icon": "🥵", "text": f"Hot today — high of {today['high']}°F, stay hydrated"})
    if today["low"] <= FREEZE_F:
        notices.append({"level": "moderate", "icon": "🥶", "text": f"Freezing temperatures — low of {today['low']}°F"})
    return cur, today, notices


def _plus_hours(hour_str, n):
    t = time.strptime(hour_str, "%Y-%m-%dT%H")
    return time.strftime("%Y-%m-%dT%H", time.localtime(time.mktime(t) + n * 3600))


def nws_alerts(lat, lon):
    j = get_json(f"https://api.weather.gov/alerts/active?point={lat},{lon}")
    rank = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}
    out = []
    for f in j.get("features", []):
        p = f.get("properties", {})
        sev = p.get("severity", "Unknown")
        out.append({
            "level": {"Extreme": "severe", "Severe": "severe", "Moderate": "moderate"}.get(sev, "minor"),
            "icon": "⚠️",
            "text": p.get("headline") or p.get("event") or "Weather alert",
            "event": p.get("event", ""), "severity": sev, "_r": rank.get(sev, 9),
        })
    out.sort(key=lambda a: a["_r"])
    for a in out:
        a.pop("_r")
    return out


def main():
    conf = read_conf(CONF)
    lat, lon = conf.get("LATITUDE", "40.7128"), conf.get("LONGITUDE", "-74.0060")
    try:
        cur, today, notices = weather(lat, lon)
    except Exception as e:
        print(f"Open-Meteo FAILED ({e}); keeping previous weather.json", file=sys.stderr)
        return 1
    try:
        alerts = nws_alerts(lat, lon)
    except Exception as e:                  # alerts are a bonus; never lose the forecast over them
        print(f"NWS alerts FAILED ({e})", file=sys.stderr)
        alerts = []
    data = {"updated": int(time.time()), "current": cur, "today": today, "alerts": alerts + notices}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), prefix=".weather-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)
    print(f"{cur['icon']} {cur['temp']}°F {cur['text']} · H {today['high']} L {today['low']} · {len(alerts)} NWS alert(s), {len(notices)} notice(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
