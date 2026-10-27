"""TMDB helper: cast, director, trailer and where-to-watch (with logos) in one call."""
import os
import requests

# Jio/Airtel Block bypass karne ke liye TMDB ka alternate domain
BASE = "https://api.tmdb.org/3"

def details(tmdb_id, country="IN"):
    """None if no TMDB_API_KEY is set."""
    key = os.getenv("TMDB_API_KEY", "").strip()
    if not key:
        return None
    headers, params = {}, {"append_to_response": "credits,videos,watch/providers"}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key
        
    r = requests.get(f"{BASE}/movie/{tmdb_id}", headers=headers, params=params, timeout=12)
    r.raise_for_status()
    d = r.json()
    
    cast = [{"name": c["name"], "role": c.get("character", ""), "img": c.get("profile_path")}
            for c in d.get("credits", {}).get("cast", [])[:14]]
    director = next((c["name"] for c in d.get("credits", {}).get("crew", []) if c.get("job") == "Director"), "")
    vids = [v for v in d.get("videos", {}).get("results", []) if v["site"] == "YouTube" and v["type"] in ("Trailer", "Teaser")]
    vids.sort(key=lambda v: v["type"] != "Trailer")
    wp = d.get("watch/providers", {}).get("results", {}).get(country, {})
    prov = lambda k: [{"name": p["provider_name"], "logo": p.get("logo_path")} for p in wp.get(k, [])]
    
    return {"tagline": d.get("tagline", ""), "backdrop": d.get("backdrop_path"), "cast": cast, "director": director,
            "trailer": vids[0]["key"] if vids else None,
            "stream": prov("flatrate"), "rent": prov("rent"), "buy": prov("buy"), "link": wp.get("link")}