# CineSense (standalone website)

Double-click START.bat. That's it.
- First time it installs the packages, asks for your keys once (you can skip them), and builds the movie index
  (you pick the TMDB dataset .csv/.zip in a normal file dialog; nothing to copy anywhere).
- After that START.bat just opens the website (http://127.0.0.1:8000).

Parts:  static/ = website | server.py = backend (accounts, history, engine.py, ott.py, db.py)
        ai_service.py = the AI model, kept separate (embeddings + FAISS + Gemini)
To rebuild the index: delete the index_data folder and run START.bat again.
