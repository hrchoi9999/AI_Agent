# Development Environment

This workspace uses the root-level Python virtual environment at `.venv`.

## Activate

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Command Prompt:

```bat
.\.venv\Scripts\activate.bat
```

## Install Dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Verify

```powershell
.\.venv\Scripts\python.exe check_environment.py
```

## PDF Question Generator

Install or refresh dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the Streamlit app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run main_pdf.py
```

The app works with a basic local question generator by default. To use AI
question generation, create a local `.env` file with:

```text
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Optional Selenium browser smoke test:

```powershell
.\.venv\Scripts\python.exe selenium_smoke_test.py
```

Optional PostgreSQL smoke test:

```powershell
.\.venv\Scripts\python.exe postgres_smoke_test.py
```

## Toddler Game Web App

This thread's game prototype lives in `toddler_game`.

Run the local Flask server:

```powershell
.\.venv\Scripts\python.exe -m flask --app toddler_game.app run --host 127.0.0.1 --port 5000 --debug
```

Open:

```text
http://127.0.0.1:5000/
```

Run Python tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

Run the responsive Selenium smoke test:

```powershell
.\.venv\Scripts\python.exe toddler_game_selenium_smoke_test.py
```

## Fridge Recipe Web App

This thread's fridge clean-out recipe app lives in `fridge_recipe_app`.

Run the local Flask server:

```powershell
.\.venv\Scripts\python.exe -m flask --app fridge_recipe_app.app run --host 127.0.0.1 --port 5001 --debug
```

Open:

```text
http://127.0.0.1:5001/
```

Run its tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_fridge_recipe_app.py
```

Current MVP behavior:

- Upload a refrigerator image and/or type visible ingredients.
- Summarize detected ingredients using a replaceable local recognizer stub.
- Recommend recipes by matching owned ingredients against the recipe catalog.
- Save scans to PostgreSQL when `DATABASE_URL` points to an initialized database.

### Cloudflare Deployment

The Cloudflare Workers deployment package lives in `cloudflare/frideg_recipe`.
Cloudflare Worker names cannot contain underscores, so the shortened public
Worker URL name is deployed as `fridge`.

Current deployed URL:

```text
https://fridge.hrchoi.workers.dev
```

Deploy again:

```powershell
cd cloudflare\frideg_recipe
npm.cmd run deploy
```

Cloudflare Pages deployment, matching the `*.pages.dev` style used by
`ttugi-intro.pages.dev`, is also configured with Pages Functions.

Current Pages URL:

```text
https://fridge-45f.pages.dev
```

Deploy Pages again:

```powershell
cd cloudflare\frideg_recipe
npm.cmd run deploy:pages
```

## Static Fridge Web App

The rebuilt static-only version lives in `fridge_static_app`. It uses only:

- `index.html`
- `styles.css`
- `app.js`

The current visual design uses a generated kawaii 9:16 illustration:

```text
fridge_static_app/assets/kawaii-fridge.png
```

Run locally:

```powershell
cd fridge_static_app
..\.venv\Scripts\python.exe -m http.server 5010 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:5010/
```

Deploy the static version to Cloudflare Pages:

```powershell
cd fridge_static_app
npx.cmd wrangler pages deploy dist --project-name fridge --branch main
```

Gemini AI recipe generation is implemented as a Cloudflare Pages Function.
It accepts selected ingredients, notes, and an optional uploaded image, then
uses Gemini Vision to infer visible refrigerator ingredients before generating
a recipe.

```text
fridge_static_app/functions/api/ai-recipe.js
```

Local secret file:

```text
fridge_static_app/.env
```

Upload or update the production Pages secret:

```powershell
cd fridge_static_app
npx.cmd wrangler pages secret bulk .env --project-name fridge
```

Current baseline:

- Python 3.14.5
- Selenium 4.44.0
- Flask 3.1.3
- pytest 9.0.3
- psycopg 3.3.4
- Chrome and Edge are installed in the standard Windows application folders.

## PostgreSQL

PostgreSQL 17 is installed locally.

Default local development settings for the fridge recipe app:

```text
Host: localhost
Port: 5432
Admin user: postgres
Admin password: postgres
Database: fridge_recipe_db
App user: fridge_user
App password: fridge_pass
```

Connection URL:

```text
postgresql://fridge_user:fridge_pass@localhost:5432/fridge_recipe_db
```

Run the fridge recipe database setup script:

```powershell
$env:PGPASSWORD='postgres'
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h localhost -p 5432 -U postgres -d postgres -f scripts\setup_fridge_recipe_db.sql
```
