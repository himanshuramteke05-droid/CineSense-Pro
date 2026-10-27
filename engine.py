"""CineSense engine: initial profile (cold start), pattern learning, scoring."""
import math
import time

import numpy as np

GENRES = ["Action", "Adventure", "Animation", "Comedy", "Crime", "Drama", "Family", "Fantasy",
          "Horror", "Mystery", "Romance", "Science Fiction", "Thriller"]
# mood -> (genre boosts, text used for semantic search)
MOODS = {
    "Funny": ({"Comedy": 1.0, "Family": 0.5, "Animation": 0.4}, "light, funny, feel-good comedy"),
    "Emotional": ({"Drama": 1.0, "Romance": 0.6}, "emotional, touching, heartfelt story"),
    "Exciting": ({"Action": 1.0, "Adventure": 0.8, "Thriller": 0.6}, "exciting, fast-paced, thrilling"),
    "Relaxing": ({"Comedy": 0.6, "Family": 0.6, "Animation": 0.5, "Romance": 0.4}, "relaxing, easy, heartwarming"),
    "Thought-provoking": ({"Science Fiction": 1.0, "Mystery": 0.8, "Drama": 0.5, "Thriller": 0.5},
                          "thought-provoking, complex plot, mind-bending"),
    "Surprise me": ({}, "a great movie"),
}
TIMES = {"Under 90 minutes": 80, "Around 2 hours": 110, "2 to 3 hours": 150, "No preference": None}
SENSITIVE = {"Horror", "Thriller", "Crime"}  # hidden for viewers under 13


def initial_profile(mood, interests, avoid):
    """Quiz answers -> genre preference scores (0..1)."""
    p = {g: 0.3 for g in GENRES}
    for g in (interests or []):
        p[g] = 0.8
    boosts = MOODS.get(mood, ({}, ""))[0]
    for g, b in boosts.items():
        p[g] = min(1.0, p.get(g, 0.3) + 0.2 * b)
    for g in (avoid or []):
        p[g] = 0.05
    return p


def learn(base, history):
    """Blend the quiz profile with watch history. Recent ratings count more (recency factor)."""
    now, agg = time.time(), {}
    base = base or {g: 0.3 for g in GENRES}
    for h in history:
        raw_r = float(h.get("rating", 3.0))
        r = max(0.0, min(1.0, (raw_r - 1.0) / 4.0))                # 1..5 stars -> 0..1 (safely clamped)
        w = math.exp(-max(0.0, now - float(h.get("ts", now))) / 86400.0 / 30.0)  # 30-day decay
        genres_str = str(h.get("genres") or "")
        for g in genres_str.split(", "):
            g = g.strip()
            if g:
                a = agg.setdefault(g, [0.0, 0, 0.0, 0.0])
                a[0] += r
                a[1] += 1
                a[2] += r * w
                a[3] += w
    conf = min(1.0, len(history) / 10.0)                          # more history -> trust it more
    prof = dict(base)
    for g in GENRES:
        if g not in prof:
            prof[g] = 0.3
    for g, (s, n, sw, w) in agg.items():
        recent_val = (sw / w) if w > 0.0 else (s / n if n > 0 else 0.5)
        hist_val = (s / n) if n > 0 else 0.5
        learned = 0.4 * hist_val + 0.6 * recent_val               # historical x0.4 + recent x0.6
        prof[g] = (1.0 - conf) * prof.get(g, 0.3) + conf * learned
    return prof, conf


def confidence_label(n):
    return "Low" if n < 3 else "Medium" if n < 10 else "High"


def pref_runtime(history, quiz_time):
    liked = [int(h["runtime"]) for h in (history or []) if float(h.get("rating", 0)) >= 4.0 and h.get("runtime")]
    return float(np.median(liked)) if len(liked) >= 3 else TIMES.get(quiz_time)


def rank(c, profile, mood, pref_rt, langs, age, avoid):
    """Score candidates (DataFrame with sim, latest_sim, genres, runtime, vote_*, language)."""
    boost = MOODS.get(mood, ({}, ""))[0]
    c = c.copy()
    young = age is not None and age < 13
    avoid_set = set(avoid or [])
    
    # Safe genres splitting and filtering
    def is_bad(s):
        gs = [g.strip() for g in str(s or "").split(", ") if g.strip()]
        return any(g in avoid_set or (young and g in SENSITIVE) for g in gs)

    bad = c["genres"].map(is_bad)
    c = c[~bad].copy()
    if c.empty:
        return c

    norm = lambda x: np.clip((x - 0.15) / 0.5, 0.0, 1.0)
    
    def score_genres_hist(s):
        gs = [g.strip() for g in str(s or "").split(", ") if g.strip()]
        return float(np.mean([profile.get(g, 0.3) for g in gs] or [0.3]))

    def score_genres_mood(s):
        if not boost:
            return 0.5
        gs = [g.strip() for g in str(s or "").split(", ") if g.strip()]
        scores = [boost.get(g, 0.0) for g in gs]
        return float(max(scores)) if scores else 0.0

    c["f_hist"] = c["genres"].map(score_genres_hist)
    c["f_mood"] = c["genres"].map(score_genres_mood)
    c["f_sim"] = norm(c["sim"].fillna(0.0))
    c["f_latest"] = norm(c["latest_sim"].fillna(0.0))
    
    vote_avg = c["vote_average"].fillna(5.0)
    vote_cnt = c["vote_count"].fillna(0.0)
    c["f_pop"] = 0.5 * (vote_avg / 10.0) + 0.5 * np.minimum(np.log10(vote_cnt + 1.0) / 5.0, 1.0)
    
    if pref_rt:
        rt = c["runtime"].fillna(pref_rt)
        c["f_rt"] = 1.0 - np.minimum((rt - pref_rt).abs() / 60.0, 1.0)
    else:
        c["f_rt"] = 1.0

    if langs:
        orig_lang = c["original_language"].fillna("")
        c["f_lang"] = orig_lang.isin(langs).astype(float).clip(0.3, 1.0)
    else:
        c["f_lang"] = 1.0

    c["score"] = (.30 * c["f_hist"] + .20 * c["f_mood"] + .15 * c["f_sim"] + .10 * c["f_latest"]
                  + .10 * c["f_pop"] + .05 * c["f_rt"] + .05 * c["f_lang"] + .05)
    c["score"] = c["score"].fillna(0.0)
    return c.sort_values("score", ascending=False)


def reason(genres, profile):
    gs = [g.strip() for g in str(genres or "").split(", ") if g.strip()]
    if not gs:
        return "A well-rated pick for you."
    g = max(gs, key=lambda x: profile.get(x, 0.3))
    return f"Fits your taste for {g}."
