# CineSense

CineSense recommends movies using your preferences and watch history. The project includes a static frontend, a FastAPI backend, and a separate AI service.

## Run locally

Double-click `START.bat`. On first run it installs the packages, asks for optional Gemini and TMDB API keys, and builds the movie index if it is missing. To rebuild the index, remove `index_data` and run `START.bat` again.

## Deploy the website

The static frontend is published to GitHub Pages by `.github/workflows/pages.yml` whenever changes are pushed to `main`. In the repository settings, open **Settings → Pages** and select **GitHub Actions** as the build and deployment source.

The Pages frontend needs the Python services hosted separately; GitHub Pages cannot run FastAPI or the AI model. `render.yaml` defines two Render web services (API and AI) and persistent storage for the user database. Deploy the blueprint from the Render dashboard and set the prompted secrets there:

- AI service: `GEMINI_API_KEY`
- API service: `TMDB_API_KEY`; `SMTP_USER`, `SMTP_PASS`, and `SMTP_FROM` are optional for email notifications

The Render services use paid Standard instances and a persistent disk. Review Render's current pricing before deploying. The movie index in `index_data/` is included in this repository; the sentence-transformer weights are downloaded by the AI service at startup.

The frontend defaults to `https://cinesense-api.onrender.com`. If Render assigns a different API URL, update `window.CINESENSE_API_URL` in `static/config.js`. If the AI service URL changes, update `AI_URL` in the API service's Render environment. The API's allowed browser origin is set by `CINESENSE_CORS_ORIGINS` in `render.yaml`.

Copy `.env.example` to `.env` for local configuration. Never commit `.env` or put API keys in the frontend.
"# CineSense-Pro" 
