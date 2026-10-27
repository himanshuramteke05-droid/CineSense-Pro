"""WEBSITE BACKEND (port 8000): accounts, quiz, history, recommendation engine, OTT, serves the website.
The AI model lives in a separate service (ai_service.py); this server only calls it over HTTP."""
import json
import os
import secrets
import threading
import time
from datetime import date
from types import SimpleNamespace

import pandas as pd
import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import engine
import notify
import ott

load_dotenv()
AI = os.getenv("AI_URL", "http://127.0.0.1:8001")
LANGS = {"en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu", "ml": "Malayalam", "kn": "Kannada",
         "bn": "Bengali", "mr": "Marathi", "pa": "Punjabi", "ko": "Korean", "ja": "Japanese", "fr": "French",
         "es": "Spanish"}
WITH = ["Myself", "Friends", "Family", "Partner", "Children", "Everyone"]
LAST = {}      # user id -> context of their latest recommendation (for /api/explain)
SESSIONS = {}  # token -> user id (cleared when the server restarts)
db.init()
app = FastAPI(title="CineSense")


class Auth(BaseModel):
    name: str
    password: str
    dob: str = "2002-01-01"
    email: str = ""


class Quiz(BaseModel):
    mood: str
    interests: list[str] = []
    time: str = "No preference"
    langs: list[str] = []
    avoid: list[str] = []


class Rec(BaseModel):
    mood: str = "Surprise me"
    with_: str = "Myself"
    k: int = 5
    ai: bool = True


class Rate(BaseModel):
    id: int
    title: str
    genres: str = ""
    runtime: int = 0
    rating: float
    review: str = ""
    poster_path: str = ""


class Mark(BaseModel):
    kind: str
    on: bool
    movie: dict



def current(authorization: str = Header(None)):
    uid = SESSIONS.get((authorization or "").replace("Bearer ", "").strip())
    user = db.get_user(uid) if uid else None
    if not user:
        raise HTTPException(401, "Please log in.")
    return user


def token_for(user):
    t = secrets.token_urlsafe(24)
    SESSIONS[t] = user["id"]
    return {"token": t}


def ai(path, payload=None, params=None):
    """Call the AI service."""
    try:
        r = (requests.post(AI + path, json=payload, timeout=90) if payload is not None
             else requests.get(AI + path, params=params, timeout=60))
    except requests.ConnectionError:
        raise HTTPException(503, "The AI service is not running. Start it first (use run.bat).")
    if r.status_code != 200:
        raise HTTPException(502, str(r.json().get("detail", "AI service error")))
    return r.json()


@app.post("/api/register")
def register(a: Auth):
    if len(a.name.strip()) < 3 or len(a.password) < 4:
        raise HTTPException(400, "Username needs 3+ characters and the password 4+.")
    try:
        date.fromisoformat(a.dob)
    except ValueError:
        raise HTTPException(400, "Enter a valid date of birth.")
    if a.email and not notify.EMAIL_RE.match(a.email.strip()):
        raise HTTPException(400, "Enter a valid email address.")
    user = db.register(a.name, a.password, a.dob, a.email.strip())
    if not user:
        raise HTTPException(400, "That username is already taken.")
    return token_for(user)


@app.post("/api/login")
def login(a: Auth):
    user = db.login(a.name, a.password)
    if not user:
        raise HTTPException(400, "Wrong username or password.")
    return token_for(user)


@app.get("/api/me")
def me(u=Depends(current)):
    return {"name": u["name"].title(), "email": u["email"], "has_quiz": "base" in u["prefs"], "moods": list(engine.MOODS),
            "genres": engine.GENRES, "times": list(engine.TIMES), "langs": LANGS, "with": WITH}


@app.post("/api/quiz")
def quiz(q: Quiz, u=Depends(current)):
    if q.mood not in engine.MOODS:
        raise HTTPException(400, "Unknown mood.")
    db.save_prefs(u["id"], {"base": engine.initial_profile(q.mood, q.interests, q.avoid),
                            "time": q.time, "langs": q.langs, "avoid": q.avoid})
    return {"ok": True}


@app.post("/api/quiz/reset")
def quiz_reset(u=Depends(current)):
    db.save_prefs(u["id"], {})
    return {"ok": True}


@app.post("/api/recommend")
def recommend(req: Rec, u=Depends(current)):
    prefs = u["prefs"]
    if "base" not in prefs:
        raise HTTPException(400, "Please take the quiz first.")
    if req.mood not in engine.MOODS:
        raise HTTPException(400, "Unknown mood.")
    hist = db.get_history(u["id"])
    age = (date.today() - date.fromisoformat(u["dob"])).days // 365
    profile, _ = engine.learn(prefs["base"], hist)                       # pattern learning
    top = sorted(profile, key=profile.get, reverse=True)[:3]
    found = ai("/retrieve", {"text": f"{engine.MOODS[req.mood][1]}. Genres: {', '.join(top)}",   # RAG retrieval
                             "latest_id": hist[-1]["mid"] if hist else None,
                             "exclude_ids": [h["mid"] for h in hist], "n": 500})
    cands = pd.DataFrame(found["candidates"])
    if cands.empty:
        return {"movies": [], "ai_error": None}
    ranked = engine.rank(cands, profile, req.mood, engine.pref_runtime(hist, prefs.get("time")),     # recommendation engine
                         prefs.get("langs", []), age, prefs.get("avoid", [])).head(max(1, min(req.k, 10)))
    movies = json.loads(ranked.to_json(orient="records"))
    liked = [h["title"] for h in hist if h["rating"] >= 4][-5:]
    LAST[u["id"]] = ("User taste (genre preference 0-1): " + ", ".join(f"{g} {profile[g]:.2f}" for g in top)
                     + f". Mood today: {req.mood}. Watching with: {req.with_}. "
                     + f"Recently loved: {', '.join(liked) or 'nothing yet (new user)'}.")
    for m in movies:                       # instant fallback reason; real AI reasons arrive via /api/explain
        m["why"] = engine.reason(m["genres"], profile)
        m["strength"] = round(min(1.0, m["score"] / .8), 2)
    return {"movies": movies}


@app.post("/api/rate")
def rate(r: Rate, u=Depends(current)):
    if not 0.5 <= r.rating <= 5 or (r.rating * 2) % 1:
        raise HTTPException(400, "Rating must be 0.5 to 5 in half-star steps.")
    db.add_history(u["id"], SimpleNamespace(id=r.id, title=r.title, genres=r.genres, runtime=r.runtime), r.rating,
                   r.review.strip()[:2000], r.poster_path)
    db.set_mark(u["id"], r.id, "watchlist", False)          # watched films leave the watchlist
    return {"ok": True}


@app.post("/api/mark")
def mark(r: Mark, u=Depends(current)):
    if r.kind not in ("watchlist", "like") or "id" not in r.movie:
        raise HTTPException(400, "Bad request.")
    keep = ("id", "title", "year", "genres", "runtime", "poster_path", "vote_average", "overview", "original_language")
    db.set_mark(u["id"], r.movie["id"], r.kind, r.on, {k: r.movie.get(k) for k in keep})
    return {"ok": True}


@app.get("/api/marks")
def marks(u=Depends(current)):
    return db.get_marks(u["id"])


@app.get("/api/diary")
def diary(u=Depends(current)):
    return {"entries": [{"mid": h["mid"], "title": h["title"], "genres": h["genres"], "runtime": h["runtime"], "rating": h["rating"],
                         "ts": h["ts"], "review": h.get("note") or "", "poster": h.get("poster") or ""}
                        for h in sorted(db.get_history(u["id"]), key=lambda x: -x["ts"])]}


@app.get("/api/taste")
def taste(u=Depends(current)):
    hist = db.get_history(u["id"])
    profile, _ = engine.learn(u["prefs"].get("base", {}), hist)
    top = sorted(profile.items(), key=lambda kv: -kv[1])[:8]
    return {"confidence": engine.confidence_label(len(hist)), "count": len(hist),
            "profile": [{"genre": g, "score": round(s, 2)} for g, s in top],
            "history": [{"title": h["title"], "rating": h["rating"], "genres": h["genres"], "ts": h["ts"]}
                        for h in reversed(hist)]}


class ExplainReq(BaseModel):
    items: list[dict]


@app.post("/api/explain")
def explain(r: ExplainReq, u=Depends(current)):
    items = [{"title": m.get("title", ""), "year": m.get("year", 0), "genres": m.get("genres", ""),
              "overview": m.get("overview", "")} for m in r.items[:10]]
    return ai("/explain", {"context": LAST.get(u["id"], ""), "items": items})


@app.get("/api/movie/{mid}")
def movie(mid: int, country: str = "IN", u=Depends(current)):
    try:
        d = ott.details(mid, country)
    except Exception:
        raise HTTPException(502, "Could not reach TMDB right now.")
    return {"configured": d is not None, **(d or {})}


@app.get("/api/showcase")
def showcase():
    try:
        return ai("/search", params={"q": "acclaimed epic blockbuster film", "k": 24})
    except HTTPException:
        return {"movies": []}


class EmailReq(BaseModel):
    email: str


@app.post("/api/email")
def set_email(r: EmailReq, u=Depends(current)):
    if r.email and not notify.EMAIL_RE.match(r.email.strip()):
        raise HTTPException(400, "Enter a valid email address.")
    db.set_email(u["id"], r.email.strip())
    return {"ok": True}


@app.post("/api/notify/test")
def notify_test(u=Depends(current)):
    """Send ME an alert right now (demo button). Uses a lower match threshold and ignores 'already sent'."""
    if not u["email"]:
        raise HTTPException(400, "Save your email first.")
    try:
        return notify.run(only_uid=u["id"], test=True)
    except RuntimeError as e:                       # missing TMDB/SMTP settings
        raise HTTPException(400, str(e))
    except Exception as e:                          # TMDB down, bad SMTP login, etc.
        raise HTTPException(502, f"Could not send: {type(e).__name__}: {str(e)[:160]}")


def _daily():
    while True:
        try:
            print("[notify]", notify.run())
        except Exception as e:
            print("[notify] error:", e)
        time.sleep(86400)


if os.getenv("NOTIFY_DAILY", "1") == "1":
    threading.Thread(target=_daily, daemon=True).start()


@app.get("/api/search")
def search(q: str, u=Depends(current)):
    return ai("/search", params={"q": q, "k": 6})


@app.get("/")
def home():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
