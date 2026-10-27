"""Step 1 (run once): TMDB CSV -> preprocessing -> embeddings -> FAISS index.

Usage:
  python build_index.py --csv TMDB_movie_dataset_v11.csv            # full build
  python build_index.py --csv TMDB_movie_dataset_v11.csv --limit 3000   # quick test
The CSV can also be the .zip you downloaded; pandas reads it directly.
"""
import argparse
from pathlib import Path

import pandas as pd

OUT = Path("index_data")
COLS = ["id", "title", "vote_average", "vote_count", "release_date", "runtime", "adult",
        "original_language", "overview", "poster_path", "genres", "keywords", "tagline"]
KEEP = ["id", "title", "year", "runtime", "vote_average", "vote_count",
        "original_language", "genres", "overview", "poster_path"]


def load(csv, min_votes=50, limit=None):
    """Read in chunks (the CSV is ~660 MB), keep only good, displayable movies."""
    parts = []
    for chunk in pd.read_csv(csv, usecols=COLS, chunksize=200_000):
        chunk = chunk.dropna(subset=["title", "overview", "poster_path"])
        chunk = chunk[(chunk["vote_count"] >= min_votes)
                      & (chunk["adult"].astype(str).str.lower() != "true")
                      & (chunk["overview"].str.len() > 30)]
        parts.append(chunk)
    df = pd.concat(parts, ignore_index=True).drop_duplicates("id")
    df = df.sort_values("vote_count", ascending=False)
    if limit:
        df = df.head(limit)
    for c in ["genres", "keywords", "tagline"]:
        df[c] = df[c].fillna("")
    df["runtime"] = df["runtime"].fillna(0).astype(int)
    df["year"] = pd.to_numeric(df["release_date"].str[:4], errors="coerce").fillna(0).astype(int)
    # One text per movie: this is what gets embedded.
    df["text"] = (df["title"] + ". Genres: " + df["genres"] + ". " + df["tagline"] + " "
                  + df["overview"] + " Keywords: " + df["keywords"].str.slice(0, 200))
    return df.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="TMDB_movie_dataset_v11.csv")
    ap.add_argument("--min-votes", type=int, default=50)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    a = ap.parse_args()

    import faiss
    from sentence_transformers import SentenceTransformer

    print("1/4 Loading and cleaning CSV ...")
    df = load(a.csv, a.min_votes, a.limit)
    print(f"    {len(df):,} movies kept")

    print("2/4 Creating embeddings (first run downloads the model) ...")
    model = SentenceTransformer(a.model)
    vecs = model.encode(df["text"].tolist(), batch_size=128, normalize_embeddings=True,
                        show_progress_bar=True).astype("float32")

    print("3/4 Building FAISS index ...")
    index = faiss.IndexFlatIP(vecs.shape[1])  # inner product == cosine (vectors are normalized)
    index.add(vecs)

    print("4/4 Saving ...")
    OUT.mkdir(exist_ok=True)
    faiss.write_index(index, str(OUT / "movies.faiss"))
    df[KEEP].to_pickle(OUT / "movies.pkl")
    (OUT / "model.txt").write_text(a.model)
    print("Done. Now run START.bat to start CineSense.")


if __name__ == "__main__":
    main()
