"""CineSense engine: initial profile (cold start), pattern learning, scoring. No Streamlit here."""
import math
import time

import numpy as np

GENRES = ["Action", "Adventure", "Animation", "Comedy", "Crime", "Drama", "Family", "Fantasy",
          "Horror", "Mystery", "Romance", "Science Fiction", "Thriller"]
# mood -> (genre boosts, text used for semantic search)
MOODS = {
    "Funny": ({"Comedy": 1, "Family": .5, "Animation": .4}, "light, funny, feel-good comedy"),
    "Emotional": ({"Drama": 1, "Romance": .6}, "emotional, touching, heartfelt story"),
    "Exciting": ({"Action": 1, "Adventure": .8, "Thriller": .6}, "exciting, fast-paced, thrilling"),
    "Relaxing": ({"Comedy": .6, "Family": .6, "Animation": .5, "Romance": .4}, "relaxing, easy, heartwarming"),
    "Thought-provoking": ({"Science Fiction": 1, "Mystery": .8, "Drama": .5, "Thriller": .5},
                          "thought-provoking, complex plot, mind-bending"),
    "Surprise me": ({}, "a great movie"),
}
TIMES = {"Under 90 minutes": 80, "Around 2 hours": 110, "2 to 3 hours": 150, "No preference": None}
SENSITIVE = {"Horror", "Thriller", "Crime"}  # hidden for viewers under 13


def initial_profile(mood, interests, avoid):
    """Quiz answers -> genre preference scores (0..1)."""
    p = {g: 0.3 for g in GENRES}
    for g in interests:
        p[g] = 0.8
    for g, b in MOODS[mood][0].items():
        p[g] = min(1.0, p[g] + 0.2 * b)
    for g in avoid:
        p[g] = 0.05
    return p


def learn(base, history):
    """Blend the quiz profile with watch history. Recent ratings count more (recency factor)."""
    now, agg = time.time(), {}
    for h in history:
        r = (h["rating"] - 1) / 4                                  # 1..5 stars -> 0..1
        w = math.exp(-max(0, now - h["ts"]) / 86400 / 30)          # 30-day decay
        for g in h["genres"].split(", "):
            if g:
                a = agg.setdefault(g, [0.0, 0, 0.0, 0.0])
                a[0] += r; a[1] += 1; a[2] += r * w; a[3] += w
    conf = min(1.0, len(history) / 10)                             # more history -> trust it more
    prof = dict(base)
    for g, (s, n, sw, w) in agg.items():
        learned = 0.4 * (s / n) + 0.6 * (sw / w)                   # historical x0.4 + recent x0.6
        prof[g] = (1 - conf) * base.get(g, 0.3) + conf * learned
    return prof, conf


def confidence_label(n):
    return "Low" if n < 3 else "Medium" if n < 10 else "High"


def pref_runtime(history, quiz_time):
    liked = [h["runtime"] for h in history if h["rating"] >= 4 and h["runtime"]]
    return float(np.median(liked)) if len(liked) >= 3 else TIMES.get(quiz_time)


def rank(c, profile, mood, pref_rt, langs, age, avoid):
    """Score candidates (DataFrame with sim, latest_sim, genres, runtime, vote_*, language)."""
    boost, c = MOODS[mood][0], c.copy()
    young = age is not None and age < 13
    bad = c["genres"].map(lambda s: any(g in avoid or (young and g in SENSITIVE) for g in s.split(", ")))
    c = c[~bad].copy()
    if c.empty:
        return c
    norm = lambda x: np.clip((x - .15) / .5, 0, 1)
    c["f_hist"] = c["genres"].map(lambda s: np.mean([profile.get(g, .3) for g in s.split(", ") if g] or [.3]))
    c["f_mood"] = c["genres"].map(lambda s: max([boost.get(g, 0) for g in s.split(", ")])) if boost else 0.5
    c["f_sim"], c["f_latest"] = norm(c["sim"]), norm(c["latest_sim"])
    c["f_pop"] = .5 * c["vote_average"] / 10 + .5 * np.minimum(np.log10(c["vote_count"] + 1) / 5, 1)
    c["f_rt"] = (1 - np.minimum((c["runtime"] - pref_rt).abs() / 60, 1)) if pref_rt else 1.0
    c["f_lang"] = c["original_language"].isin(langs).astype(float).clip(.3, 1) if langs else 1.0
    c["score"] = (.30 * c["f_hist"] + .20 * c["f_mood"] + .15 * c["f_sim"] + .10 * c["f_latest"]
                  + .10 * c["f_pop"] + .05 * c["f_rt"] + .05 * c["f_lang"] + .05)  # last .05 = suitability (filtered above)
    return c.sort_values("score", ascending=False)


def reason(genres, profile):
    gs = [g for g in genres.split(", ") if g]
    if not gs:
        return "A well-rated pick for you."
    g = max(gs, key=lambda x: profile.get(x, .3))
    return f"Fits your taste for {g}."
