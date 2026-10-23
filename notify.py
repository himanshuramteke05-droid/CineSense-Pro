"""Email alerts: new/upcoming movies (TMDB) are scored against each user's Movie DNA; only matching users get an email."""
import os
import re
import smtplib
import traceback
from html import escape
from datetime import date
from email.message import EmailMessage

import requests

import db
import engine

GID = {28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime", 18: "Drama", 10751: "Family",
       14: "Fantasy", 27: "Horror", 9648: "Mystery", 10749: "Romance", 878: "Science Fiction", 53: "Thriller"}


def fresh_movies(region="IN"):
    key = os.getenv("TMDB_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TMDB_API_KEY is empty in .env")
    h, p = {}, {"region": region}
    if key.startswith("eyJ"):
        h["Authorization"] = f"Bearer {key}"
    else:
        p["api_key"] = key
    out = {}
    for kind in ("upcoming", "now_playing"):
        r = requests.get(f"https://api.tmdb.org/3/movie/{kind}", headers=h, params=p, timeout=12)
        r.raise_for_status()
        for m in r.json().get("results", []):
            if m.get("poster_path") and m.get("overview"):
                m["genres"] = [GID[g] for g in m.get("genre_ids", []) if g in GID]
                out[m["id"]] = m
    return list(out.values())


def match(m, profile, prefs, age):
    """Genre-match score 0..1, or None if this movie must not be sent to this user."""
    gs = m["genres"]
    if not gs or any(g in prefs.get("avoid", []) for g in gs):
        return None
    if age is not None and age < 13 and any(g in engine.SENSITIVE for g in gs):
        return None
    if prefs.get("langs") and m.get("original_language") not in prefs["langs"]:
        return None
    return sum(profile.get(g, .3) for g in gs) / len(gs)


def send(to, name, picks):
    host, user, pw = os.getenv("SMTP_HOST", "smtp.gmail.com"), os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASS", "")
    port = int(os.getenv("SMTP_PORT", "465"))
    sender = os.getenv("SMTP_FROM", user)
    
    if not (host and user and pw):
        raise RuntimeError("SMTP_HOST / SMTP_USER / SMTP_PASS are empty in .env")
        
    rows = "".join(
        f'<tr><td style="padding:10px;vertical-align:top"><img src="https://image.tmdb.org/t/p/w185{m["poster_path"]}" width="90" style="border-radius:8px"></td>'
        f'<td style="padding:10px"><b style="font-size:16px">{escape(m["title"])}</b><br>'
        f'<span style="color:#777">{escape(", ".join(m["genres"]))} &middot; releases {escape(m.get("release_date") or "soon")}</span><br>'
        f'<span>{escape((m.get("overview") or "")[:180])}...</span><br>'
        f'<i style="color:#b8860b">{escape(why)} Match {round(s * 100)}%.</i></td></tr>'
        for s, m, why in picks)
    msg = EmailMessage()
    msg["Subject"] = f"{picks[0][1]['title']} and {len(picks) - 1} more movies picked for you" if len(picks) > 1 else f"New for you: {picks[0][1]['title']}"
    msg["From"], msg["To"] = sender, to
    msg.set_content("New movies matching your taste are out. Open CineSense to see them.")
    msg.add_alternative(f'<div style="font-family:Arial;max-width:560px"><h2>Hi {name.title()}, new movies for your taste</h2>'
                        f'<table>{rows}</table><p style="color:#888">Sent by CineSense because these match your Movie DNA.</p></div>', subtype="html")
    
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=25) as s:
                s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=25) as s:
                s.starttls()
                s.login(user, pw)
                s.send_message(msg)
    except Exception as e:
        raise Exception(f"Could not send: {str(e)}")


def run(only_uid=None, test=False):
    movies = fresh_movies()
    bar, sent_total, users_mailed, errors = (.5 if test else .72), 0, 0, []
    for row in ([{"id": only_uid}] if only_uid else db.users_with_email()):
        u = db.get_user(row["id"])
        if not u or not u["email"] or "base" not in u["prefs"]:
            continue
        hist = db.get_history(u["id"])
        profile, _ = engine.learn(u["prefs"]["base"], hist)
        age = (date.today() - date.fromisoformat(u["dob"])).days // 365
        seen = set() if test else db.sent_ids(u["id"])
        picks = []
        for m in movies:
            s = None if m["id"] in seen else match(m, profile, u["prefs"], age)
            if s is not None and s >= bar:
                picks.append((s, m, engine.reason(", ".join(m["genres"]), profile)))
        picks = sorted(picks, key=lambda x: -x[0])[:3]
        if picks:
            try:
                send(u["email"], u["name"], picks)
            except Exception as e:
                if test:
                    raise
                errors.append(f"{u['name']}: {e}")
                continue
            if not test:
                db.mark_sent(u["id"], [m["id"] for _, m, _ in picks])
            sent_total += len(picks)
            users_mailed += 1
    return {"emails_sent": users_mailed, "movies_included": sent_total, "checked_movies": len(movies), "errors": errors}


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")