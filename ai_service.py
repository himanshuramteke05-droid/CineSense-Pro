"""AI SERVICE (port 8001): embeddings + FAISS retrieval (RAG) + LLM."""
import json
import os
import re
import time
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

load_dotenv()
DATA = Path(__file__).parent / "index_data"
PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

app = FastAPI(title="CineSense AI service")
model = SentenceTransformer((DATA / "model.txt").read_text().strip())
index = faiss.read_index(str(DATA / "movies.faiss"))
movies = pd.read_pickle(DATA / "movies.pkl")
ID_ROW = {int(i): r for r, i in enumerate(movies["id"])}


def embed(text):
    return model.encode([text], normalize_embeddings=True).astype("float32")


def records(df):
    return json.loads(df.to_json(orient="records"))


def ask_llm(prompt):
    if PROVIDER == "gemini":
        from google import genai
        from google.genai import types
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is empty in the .env file")
        client, last = genai.Client(api_key=key), None
        chain = [os.getenv("GEMINI_MODEL", "gemini-flash-latest"), "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-3.8-flash"]
        for name in dict.fromkeys(chain):                      # try each model, retry busy/rate-limited calls
            kw = dict(response_mime_type="application/json", temperature=0.6)
            for attempt in range(4):
                try:
                    txt = client.models.generate_content(model=name, contents=prompt,
                                                         config=types.GenerateContentConfig(**kw)).text
                    if txt:
                        return txt
                    last = RuntimeError("Gemini returned an empty answer")
                    break
                except Exception as e:
                    last = e
                    if any(x in str(e) for x in ("429", "500", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED")) and attempt < 3:
                        time.sleep(2 ** (attempt + 1))
                        continue
                    break
        raise last
    if PROVIDER == "claude":
        import anthropic
        r = anthropic.Anthropic().messages.create(model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"), max_tokens=900,
                                                  messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    if PROVIDER == "openai":
        from openai import OpenAI
        r = OpenAI().chat.completions.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                                             messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content
    if PROVIDER == "ollama":
        import requests
        r = requests.post("http://localhost:11434/api/generate", timeout=180, json={
            "model": os.getenv("OLLAMA_MODEL", "llama3.1"), "prompt": prompt, "stream": False})
        return r.json()["response"]
    raise ValueError(f"Unknown LLM_PROVIDER: {PROVIDER}")


class Retrieve(BaseModel):
    text: str
    latest_id: int | None = None
    exclude_ids: list[int] = []
    n: int = 500


class Item(BaseModel):
    title: str
    year: int = 0
    genres: str = ""
    overview: str = ""


class Explain(BaseModel):
    context: str
    items: list[Item]


@app.get("/health")
def health():
    return {"ok": True, "movies": len(movies), "llm": PROVIDER}


@app.get("/llm-check")
def llm_check():
    """Open http://127.0.0.1:8001/llm-check to see the exact reason if explanations fail."""
    try:
        return {"ok": True, "reply": ask_llm('Reply with JSON {"ok": true}')[:80]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}


@app.post("/retrieve")
def retrieve(r: Retrieve):
    """Semantic search (FAISS). Also returns each candidate's similarity to the user's latest watched movie."""
    sims, ids = index.search(embed(r.text), r.n)
    ok = (ids[0] >= 0) & (ids[0] < len(movies))
    c = movies.iloc[ids[0][ok]].copy()
    c["sim"] = sims[0][ok]
    c = c[~c["id"].isin(r.exclude_ids)]
    c["latest_sim"] = 0.0
    row = ID_ROW.get(r.latest_id)
    if row is not None and len(c):
        try:
            lv = index.reconstruct(row)
            candidate_rows = [ID_ROW[int(mid)] for mid in c["id"] if int(mid) in ID_ROW]
            if len(candidate_rows) == len(c):
                c["latest_sim"] = np.stack([index.reconstruct(i) for i in candidate_rows]) @ lv
        except Exception:
            c["latest_sim"] = 0.0
    return {"candidates": records(c)}


@app.get("/search")
def search(q: str, k: int = 6):
    sims, ids = index.search(embed(q), max(1, k))
    ok = (ids[0] >= 0) & (ids[0] < len(movies))
    d = movies.iloc[ids[0][ok]].copy()
    d["sim"] = sims[0][ok]
    return {"movies": records(d)}


@app.post("/explain")
def explain(r: Explain):
    """RAG + GenAI: retrieved movie info and user context go to the LLM, which explains each pick."""
    if not r.items:
        return {"reasons": {}}
    lines = "\n".join(f"{i}. {m.title} ({m.year}) [{m.genres}] {m.overview[:300]}" for i, m in enumerate(r.items, 1))
    prompt = ("You are CineSense, a movie recommendation assistant.\n" + (r.context or "") +
              "\n\nFor each numbered movie below write ONE sentence (max 30 words) addressed to the user "
              "('you') explaining why it fits their taste and mood. Use only the movie info given; do not invent facts.\n"
              f"{lines}\n\nReturn ONLY JSON like " + '{"1": "reason", "2": "reason"}')
    try:
        reply = ask_llm(prompt).strip()
        if "```" in reply:
            reply = re.sub(r"^```(?:json)?\s*", "", reply.strip(), flags=re.MULTILINE)
            reply = re.sub(r"\s*```$", "", reply.strip(), flags=re.MULTILINE)
        m = re.search(r"\{.*\}", reply, re.S)
        raw = m.group() if m else reply
        parsed = json.loads(raw)
        reasons = {}
        if isinstance(parsed, dict):
            for k, v in parsed.items():
                if k == "reasons" and isinstance(v, dict):
                    for subk, subv in v.items():
                        reasons[str(subk)] = str(subv)
                elif k == "reasons" and isinstance(v, list):
                    for idx, val in enumerate(v, 1):
                        reasons[str(idx)] = str(val)
                else:
                    reasons[str(k)] = str(v)
        elif isinstance(parsed, list):
            for idx, val in enumerate(parsed, 1):
                reasons[str(idx)] = str(val)
        return {"reasons": reasons}
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {str(e)[:200]}")
