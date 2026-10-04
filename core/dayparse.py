"""Turn what a technician says ("vendredi", "not before next Monday") into a sim day.

Resolved against the simulated calendar. Unclear input returns day=None plus a question the voice
agent can speak back, in the technician's language.
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from core.simcal import CALENDAR_START, day_date

MAX_AHEAD = 60  # days; anything further out is treated as a misheard date

WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6,
}
EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
FR_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}
NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}
UNITS_DAYS = {"day": 1, "days": 1, "jour": 1, "jours": 1, "week": 7, "weeks": 7, "semaine": 7, "semaines": 7}

ASK = {
    "en": "Sorry, I didn't catch the day. Which day can you do?",
    "fr": "Désolé, je n'ai pas compris le jour. Quel jour pouvez-vous ?",
}


@dataclass
class DayParse:
    day: int | None
    clarify: str | None = None  # spoken follow-up when day is None


def weekday_name(day: int, lang: str = "en") -> str:
    idx = day_date(day).weekday()
    return FR_DAYS[idx] if lang == "fr" else EN_DAYS[idx]


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("\u2019", "'").replace("'", " ").replace("-", " ")
    return re.sub(r"[^a-z0-9 ]+", " ", t)


def resolve_day(text: str, today: int, lang: str = "en") -> DayParse:
    """Parse a spoken day. `today` is the current sim day. Never raises."""
    lang = "fr" if lang == "fr" else "en"
    unclear = DayParse(None, ASK[lang])
    t = _norm(text or "")
    toks = t.split()
    if not toks:
        return unclear
    today_wd = day_date(today).weekday()

    def ok(day: int) -> DayParse:
        return DayParse(day) if today <= day <= today + MAX_AHEAD else unclear

    # Relative words. "day after tomorrow" must be checked before "tomorrow".
    if re.search(r"\b(day after tomorrow|apres demain|surlendemain)\b", t):
        return ok(today + 2)
    if re.search(r"\b(tomorrow|demain)\b", t):
        return ok(today + 1)
    if re.search(r"\b(today|tonight|aujourd hui)\b", t):
        return ok(today)

    # "in 3 days", "dans deux jours", "in a week"
    m = re.search(r"\b(?:in|dans)\s+(\w+)\s+(day|days|jour|jours|week|weeks|semaine|semaines)\b", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUMBERS.get(m.group(1))
        if n:
            return ok(today + n * UNITS_DAYS[m.group(2)])

    # Calendar date: "October 20", "20th of October", "le 20 octobre"
    month_pat = "|".join(sorted(MONTHS, key=len, reverse=True))
    m = (re.search(rf"\b({month_pat})\s+(\d{{1,2}})(?:st|nd|rd|th|er|e)?\b", t)
         or re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th|er|e)?\s+(?:of\s+|de\s+)?({month_pat})\b", t))
    if m:
        a, b = m.groups()
        month, dom = (MONTHS[a], int(b)) if a in MONTHS else (MONTHS[b], int(a))
        try:
            target = date(day_date(today).year, month, dom)
        except ValueError:
            return unclear
        return ok((target - CALENDAR_START).days)

    # Weekday, with optional "next"/"prochain", "this"/"ce", "after"/"apres"
    wd_idx = next((i for i, w in enumerate(toks) if w in WEEKDAYS), None)
    if wd_idx is not None:
        wd = WEEKDAYS[toks[wd_idx]]
        delta = (wd - today_wd) % 7
        has_next = bool({"next", "prochain", "prochaine"} & set(toks))
        has_this = bool({"this", "ce", "cette"} & set(toks))
        after = bool({"after", "apres"} & set(toks[max(0, wd_idx - 2):wd_idx]))
        if has_next:
            # The coming one, unless it falls in this same Monday-to-Sunday week: then the week after.
            delta = 7 if delta == 0 else (delta + 7 if today_wd + delta <= 6 else delta)
        elif delta == 0 and not has_this:
            day_txt = weekday_name(today, lang)
            q = (f"Do you mean today, or next {day_txt}?" if lang == "en"
                 else f"Vous voulez dire aujourd'hui, ou {day_txt} prochain ?")
            return DayParse(None, q)
        return ok(today + delta + (1 if after else 0))

    # "next week" -> Monday of next week
    if re.search(r"\b(next week|semaine prochaine)\b", t):
        return ok(today + (7 - today_wd))

    return unclear
