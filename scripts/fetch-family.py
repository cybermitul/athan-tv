#!/usr/bin/env python3
"""Read the family calendar and reminder lists from CalDAV (Radicale) into /opt/athan/web/family.json.

Runs from root's crontab every 5 minutes. Uses a READ-ONLY CalDAV account (the "tv" user),
so a compromised kiosk can't change or delete anything on the server.

Settings in /etc/default/athan (chmod 600 -- it holds the password):
  CALDAV_URL    e.g. http://192.168.1.3:5232/family/   (the shared account's home)
  CALDAV_USER   tv
  CALDAV_PASS   ...
  FAMILY_DAYS   days of calendar to show (default 7)
  FAMILY_LISTS  optional comma list of reminder-list names to show, in order (default: all)
"""
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time

try:
    import caldav
except ImportError:
    print("python3-caldav is not installed (apt install python3-caldav)", file=sys.stderr)
    sys.exit(1)

CONF = os.environ.get("ATHAN_CONF", "/etc/default/athan")
OUT = os.environ.get("FAMILY_OUT", "/opt/athan/web/family.json")
MAX_PER_DAY = 6
MAX_PER_LIST = 14


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


def local(d):
    """date or datetime (aware or floating) -> local-time datetime, plus all_day flag."""
    if isinstance(d, dt.datetime):
        if d.tzinfo is None:                        # floating time: already local
            return d, False
        return d.astimezone().replace(tzinfo=None), False
    return dt.datetime.combine(d, dt.time()), True


def fmt_time(t):
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'PM' if t.hour >= 12 else 'AM'}"


def text(comp, key):
    v = comp.get(key)
    return str(v).strip() if v is not None else ""


def main():
    conf = read_conf(CONF)
    url, user, pw = conf.get("CALDAV_URL"), conf.get("CALDAV_USER"), conf.get("CALDAV_PASS")
    if not (url and user and pw):
        print("CALDAV_URL / CALDAV_USER / CALDAV_PASS not set in /etc/default/athan -- skipping", file=sys.stderr)
        return 0
    days = int(conf.get("FAMILY_DAYS", "7") or 7)
    want_lists = [s.strip().lower() for s in conf.get("FAMILY_LISTS", "").split(",") if s.strip()]

    client = caldav.DAVClient(url=url, username=user, password=pw, timeout=20, ssl_verify_cert=conf.get("CALDAV_CA") or True)
    collections = caldav.CalendarSet(client=client, url=url).calendars()

    today = dt.date.today()
    start = dt.datetime.combine(today, dt.time())
    end = start + dt.timedelta(days=days)
    buckets = {today + dt.timedelta(days=i): [] for i in range(days)}
    lists = []

    for col in collections:
        try:
            comps = col.get_supported_components()
        except Exception:
            comps = ["VEVENT", "VTODO"]
        try:
            name = col.get_display_name() or "List"
        except AttributeError:                      # caldav < 1.4
            name = col.name or "List"

        if "VEVENT" in comps:
            # expand=True turns recurring events into individual occurrences inside the window
            for ev in col.search(start=start, end=end, event=True, expand=True):
                c = ev.icalendar_component
                s, all_day = local(c.get("dtstart").dt)
                e_raw = c.get("dtend")
                e = local(e_raw.dt)[0] if e_raw else s + (dt.timedelta(days=1) if all_day else dt.timedelta(hours=1))
                if all_day and e <= s:
                    e = s + dt.timedelta(days=1)
                title = text(c, "summary") or "(no title)"
                day = max(s.date(), today)
                last = (e - dt.timedelta(seconds=1)).date()          # DTEND is exclusive
                while day <= last and day in buckets:
                    buckets[day].append({
                        "time": None if all_day or day != s.date() else fmt_time(s),
                        "sort": "00:00" if all_day or day != s.date() else s.strftime("%H:%M"),
                        "title": title, "cal": name,
                    })
                    day += dt.timedelta(days=1)

        if "VTODO" in comps and (not want_lists or name.lower() in want_lists):
            items = []
            for td in col.todos(include_completed=False):
                c = td.icalendar_component
                if text(c, "status").upper() in ("COMPLETED", "CANCELLED"):
                    continue
                due = c.get("due")
                due_s = None
                if due:
                    dd = local(due.dt)[0].date()
                    due_s = "Today" if dd == today else ("Overdue" if dd < today else dd.strftime("%a %-d %b"))
                prio = int(text(c, "priority") or 0)
                items.append({"title": text(c, "summary") or "(untitled)", "due": due_s,
                              "high": 1 <= prio <= 4, "_k": (not (1 <= prio <= 4), due_s is None, text(c, "summary").lower())})
            items.sort(key=lambda i: i.pop("_k"))
            lists.append({"name": name, "total": len(items), "items": items[:MAX_PER_LIST]})

    if want_lists:
        lists.sort(key=lambda l: want_lists.index(l["name"].lower()))

    out_days = []
    for d, evs in buckets.items():
        evs.sort(key=lambda e: (e["sort"], e["title"]))
        for e in evs:
            e.pop("sort")
        label = "Today" if d == today else ("Tomorrow" if d == today + dt.timedelta(days=1) else d.strftime("%A"))
        out_days.append({"date": d.isoformat(), "label": label, "sub": d.strftime("%b %-d"),
                         "today": d == today, "total": len(evs), "events": evs[:MAX_PER_DAY]})

    data = {"updated": int(time.time()), "days": out_days, "lists": lists}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), prefix=".family-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)
    n_ev = sum(d["total"] for d in out_days)
    print(f"{n_ev} event(s) in the next {days} days; lists: " + ", ".join(f"{l['name']} ({l['total']})" for l in lists))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:                      # keep the previous family.json on any failure
        print(f"FAILED: {type(e).__name__}: {e}; keeping previous family.json", file=sys.stderr)
        sys.exit(1)
