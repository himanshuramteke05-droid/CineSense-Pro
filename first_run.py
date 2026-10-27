"""One-time setup, run automatically by START.bat:
1) creates the .env file (asks for your keys once)   2) builds the movie index if it does not exist yet."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
INDEX = ROOT / "index_data" / "movies.faiss"


def make_env():
    env = ROOT / ".env"
    if env.exists():
        return
    print("\n--- Keys (asked only once; you can edit the .env file later) ---")
    print("AI explanations need a free Gemini key: https://aistudio.google.com/apikey")
    gemini = input("Gemini API key (press Enter to skip): ").strip()
    print("'Where to watch' needs a free TMDB key: https://www.themoviedb.org/settings/api")
    tmdb = input("TMDB API key (press Enter to skip): ").strip()
    env.write_text(f"LLM_PROVIDER=gemini\nGEMINI_API_KEY={gemini}\nGEMINI_MODEL=gemini-2.5-flash\nTMDB_API_KEY={tmdb}\nSMTP_HOST=smtp.gmail.com\nSMTP_PORT=587\nSMTP_USER=\nSMTP_PASS=\nSMTP_FROM=\n")


def find_dataset():
    """Use a big .csv/.zip already in this folder, otherwise let the user pick the file in a normal Windows dialog."""
    for p in list(ROOT.glob("*.csv")) + list(ROOT.glob("*.zip")):
        if p.stat().st_size > 50_000_000:
            return p
    import tkinter as tk
    from tkinter import filedialog
    win = tk.Tk()
    win.withdraw()
    win.attributes("-topmost", True)
    path = filedialog.askopenfilename(title="Select the TMDB movies dataset (.csv or .zip)",
                                      filetypes=[("Dataset", "*.csv *.zip"), ("All files", "*.*")])
    win.destroy()
    return Path(path) if path else None


def build_index():
    print("\n--- Movie index not found: building it now (one time) ---")
    csv = find_dataset()
    if not csv:
        print("No dataset selected. Run START.bat again and pick the TMDB movies file.")
        sys.exit(1)
    print(f"Dataset: {csv}\n1) Quick test: 3,000 movies (about 3 minutes)\n2) Full: all movies (10 to 30 minutes)")
    limit = [] if input("Choose 1 or 2 [1]: ").strip() == "2" else ["--limit", "3000"]
    subprocess.run([sys.executable, "build_index.py", "--csv", str(csv), *limit], cwd=ROOT, check=True)


if __name__ == "__main__":
    make_env()
    if not INDEX.exists():
        build_index()
