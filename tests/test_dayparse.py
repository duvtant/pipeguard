import pytest

from core.dayparse import resolve_day, weekday_name

TODAY = 10  # Thursday, Oct 15, 2026 (day 0 is Monday Oct 5)

EN = [
    ("Friday", 11), ("friday", 11), ("on Friday morning", 11), ("not before Friday, sorry", 11),
    ("fri", 11), ("this Friday", 11), ("Monday", 14), ("next Monday", 14), ("next Friday", 18),
    ("tomorrow", 11), ("the day after tomorrow", 12), ("today", 10), ("in 3 days", 13),
    ("in two days", 12), ("in a week", 17), ("next week", 14), ("October 20", 15), ("Oct 20th", 15),
    ("the 20th of October", 15), ("after Friday", 12), ("this Thursday", 10),
]
FR = [
    ("vendredi", 11), ("Vendredi matin", 11), ("pas avant vendredi", 11), ("demain", 11),
    ("après-demain", 12), ("apres demain", 12), ("lundi prochain", 14), ("vendredi prochain", 18),
    ("dans trois jours", 13), ("dans 2 jours", 12), ("le 20 octobre", 15), ("1er novembre", 27),
    ("la semaine prochaine", 14), ("aujourd'hui", 10), ("après vendredi", 12), ("ce jeudi", 10),
]


@pytest.mark.parametrize("text,expected", EN)
def test_resolves_english(text, expected):
    assert resolve_day(text, TODAY, "en").day == expected


@pytest.mark.parametrize("text,expected", FR)
def test_resolves_french(text, expected):
    assert resolve_day(text, TODAY, "fr").day == expected


def test_either_language_parses_regardless_of_technician_language():
    assert resolve_day("vendredi", TODAY, "en").day == 11
    assert resolve_day("Friday", TODAY, "fr").day == 11


@pytest.mark.parametrize("text", ["", "   ", "whenever", "soon", "sometime next month", "October 1",
                                  "October 40", "in 500 days", "banana", "bientôt", None])
def test_unclear_returns_a_question_not_a_guess(text):
    r = resolve_day(text, TODAY)
    assert r.day is None and "day" in r.clarify.lower()


def test_same_weekday_asks_instead_of_guessing():
    r = resolve_day("Thursday", TODAY)
    assert r.day is None and "today" in r.clarify and "next Thursday" in r.clarify
    r = resolve_day("jeudi", TODAY, "fr")
    assert r.day is None and "aujourd'hui" in r.clarify


def test_clarifying_question_follows_language():
    assert resolve_day("peut-être", TODAY, "fr").clarify.startswith("Désolé")


def test_weekday_names():
    assert weekday_name(11) == "Friday" and weekday_name(11, "fr") == "vendredi"
