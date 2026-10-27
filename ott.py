"""TMDB helper: cast, director, trailer and where-to-watch (with logos) in one call."""
import os
import requests

BASE = "https://api.tmdb.org/3"


def details(tmdb_id, country="IN"):
    """Returns movie metadata, cast, trailer, and OTT availability. None if TMDB_API_KEY is not set or movie not found."""
    key = os.getenv("TMDB_API_KEY", "").strip()
    if not key:
        return None
    headers, params = {}, {"append_to_response": "credits,videos,watch/providers"}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key
        
    try:
        r = requests.get(f"{BASE}/movie/{tmdb_id}", headers=headers, params=params, timeout=12)
        r.raise_for_status()
        d = r.json()
    except Exception:
        return None
    
    cast = [{"name": c.get("name", ""), "role": c.get("character", ""), "img": c.get("profile_path")}
            for c in d.get("credits", {}).get("cast", [])[:14]]
    director = next((c.get("name", "") for c in d.get("credits", {}).get("crew", []) if c.get("job") == "Director"), "")
    vids = [v for v in d.get("videos", {}).get("results", []) if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser")]
    vids.sort(key=lambda v: v.get("type") != "Trailer")
    
    # Safe retrieval of country providers (TMDB sometimes returns {"results": {"IN": null}})
    wp_results = d.get("watch/providers", {}).get("results", {})
    wp = (wp_results.get(country) if wp_results else None) or {}
    prov = lambda k: [{"name": p.get("provider_name", ""), "logo": p.get("logo_path")} for p in (wp.get(k) or [])]
    
    return {
        "tagline": d.get("tagline", ""),
        "backdrop": d.get("backdrop_path"),
        "cast": cast,
        "director": director,
        "trailer": vids[0]["key"] if vids else None,
        "stream": prov("flatrate"),
        "rent": prov("rent"),
        "buy": prov("buy"),
        "link": wp.get("link")
    }
