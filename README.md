# CV Analyzer

Reads CVs (PDF, scanned or not), scores each one against the job offer it
was sent for, and keeps the passages recruiters highlight, through a REST API
other projects call. RecruteHub is the first client.

A CV always belongs to an offer: the offer is what it is scored against. The
caller first saves its offer here (`PUT /v1/offers/{its id}`, with the title
and the skills ranked 1 to 5, as RecruteHub defines them), then sends CVs for
it. A CV for an offer the engine does not know is refused.

The design, with the reasoning behind the scoring rules:
https://claude.ai/code/artifact/9daf60be-c8b5-4f8c-bd7d-babb3532a226

## Run it

```sh
docker compose up -d --build
```

Where the containers cannot reach each other (seen in some GitHub
Codespaces: the migration times out connecting to Postgres), run every
service on the host's network instead; everything is then on port 8000:

```sh
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d --build
```

The web app is on http://localhost:8100 and needs no sign-in. The API's
interactive docs are on http://localhost:8100/docs. Calls from elsewhere use
the development API key `dev-key`:

```sh
curl -X PUT -H "Authorization: Bearer dev-key" -H "Content-Type: application/json" \
  -d '{"title": "Data scientist", "skills": [{"name": "Python", "priority": 1}, {"name": "SQL", "priority": 2}]}' \
  http://localhost:8100/v1/offers/offer-1
curl -H "Authorization: Bearer dev-key" -F file=@cv.pdf -F offer_ref=offer-1 -F external_ref=cand-1 \
  http://localhost:8100/v1/documents
```

| Container | What it does |
|---|---|
| api | FastAPI: the `/v1` routes, and the web app under `/app` |
| worker | reads PDFs (pdfplumber, Tesseract OCR for scans) and scores them, from a Redis queue |
| postgres | offers and their grids, documents, lines, analyses, highlights |
| redis | the job queue |
| s3 | SeaweedFS, S3-compatible storage for the PDFs (bucket `cv-analyzer`, created on the first upload) |
| migrate | runs `alembic upgrade head`, then exits |

## How a CV is scored

1. **Offer.** `PUT /v1/offers/{ref}` saves the offer and builds its grid
   from the skills and their priorities (below).
2. **Upload.** `POST /v1/documents` takes the PDF and the `offer_ref` it is
   sent for, stores it and queues it. It answers at once with the
   document's id and status `queued`.
3. **Read.** The worker extracts the text line by line. Each line gets its
   page, its section (experience, education, skills, ...) and its position
   in the text; lines read from the PDF also get their box on the page, for
   highlighting. Text the reader cannot see (white, or smaller than 4 pt) is
   dropped. A page with almost no text is read with OCR. The status becomes
   `ready`, `unreadable` (nothing to read, even with OCR) or `failed`.
4. **Score.** The worker scores the CV against its offer's grid at once.
   When the grid changes, every CV read for the offer is scored again.
5. **Highlight.** A recruiter marks passages worth −100 to +100 points each.
6. **Read the result.** `GET /v1/documents/{id}/score` or
   `GET /v1/offers/{ref}/ranking`.

### The grid

Each offer has a grid: a list of criteria. Each criterion is a group of words: its label,
its own `terms`, and the engine's synonyms for the label (`JavaScript` also
finds `JS`, `Node.js`; `SQL` finds `PostgreSQL`, `MySQL`; see
`analysis/synonyms.py`). Matching ignores case and accents and takes whole
words only, so `Go` does not match `Google`. A criterion counts once,
however often it appears.

| Field | Meaning |
|---|---|
| `points_present` | points when found, 0 or more |
| `points_absent` | points when missing, 0 or negative |

`PUT /v1/offers/{ref}` builds the grid from the offer's skills ranked 1 to 5,
as RecruteHub's offers rank them (a skill's `name` can also be sent as
RecruteHub's `language`). Only a missing core skill costs points:

| Priority | Present | Missing |
|---|---|---|
| 1 core | +1 | -20 |
| 2 important | +0.5 | 0 |
| 3 secondary | +0.1 | 0 |
| 4 CV only | +0.5 | 0 |
| 5 bonus | +0.1 | 0 |

A recruiter can then edit that grid (other words, other points) and send it
back as `criteria` in the same PUT; the grid is then taken as given. Each
change to the grid adds a version; changing only the title does not. Old
scores keep the version they used.

### The points

A CV's score is a sum of points, with no bound and no weights:

- **auto** = the points of the grid's criteria found, minus what missing
  ones cost. Each criterion counts once, however often its words appear.
- **manual** = the sum of the recruiters' highlights, each from −100 to
  +100 (not 0). Negative points mark a red flag, for example a former
  employer the company can no longer hire from. A passage counts once: a
  highlight overlapping one already scored, or with the same text as one
  scored elsewhere in the CV, is refused (`409 already_scored`).
- **total** = auto + manual. The ranking follows it.

Every analysis keeps which criteria were found, on which lines, through
which words, and what each one gained or cost. The scores rank candidates;
they never reject anyone on their own. That decision stays with a person
(GDPR, article 22).

## The web app

A React app (`web/`) the API serves under `/app`, for recruiters:

- **Offers**: create an offer with its skills ranked 1 to 5, and adjust the
  grid it builds (more words per criterion, other points).
- **Candidates**: drop CVs (several at once), then follow the ranking as they
  are read and scored: keyword, recruiter and total points, and the core
  skills each CV is missing.
- **A CV**: the PDF itself. Select a passage, type the points it is worth
  (−100 to +100, negative for a red flag, shown in red) and a comment; it
  stays highlighted on the PDF and counts in the total at once. The points
  panel shows how the total is made.
  Hovering a skill the engine found outlines the lines it was found on. A
  scanned CV is scored from the text OCR read, line by line.

It has no sign-in: with `OPEN_CLIENT` set (compose sets `dev`), requests
without an API key act as that client. Leave `OPEN_CLIENT` empty anywhere
else. The recruiter's name, typed in the header, labels their highlights.

To work on it with live reload, run the stack, then:

```sh
cd web && npm install && npm run dev   # http://localhost:5173/app/, proxies /v1 to :8100
```

## API

Every `/v1` route takes `Authorization: Bearer <API key>`. Each key belongs
to a client, and a client only ever sees its own CVs and grids. Errors look
like `{"error": {"code": "not_found", "message": "..."}}`.

| Route | What it does |
|---|---|
| `GET /v1/offers` | the offers, last updated first, with their number of CVs |
| `PUT /v1/offers/{ref}` | create or update an offer: `title`, `skills`, optional `criteria`; rescores its CVs when the grid changes |
| `GET /v1/offers/{ref}` | the offer and its latest grid |
| `DELETE /v1/offers/{ref}` | erase the offer and every CV sent for it |
| `GET /v1/offers/{ref}/ranking` | the offer's CVs, highest total first, with missing core skills |
| `POST /v1/documents` | upload a PDF (form fields `file`, `offer_ref` required, `external_ref`); 202, or 404 `offer_not_found` |
| `GET /v1/documents` | list, filtered by `offer_ref`, `external_ref`, `status` |
| `GET /v1/documents/{id}` | status, full text and lines with sections, offsets and boxes |
| `GET /v1/documents/{id}/file` | the PDF |
| `DELETE /v1/documents/{id}` | erase the PDF, text, scores and highlights |
| `POST /v1/documents/{id}/analyses` | score now against the offer's latest grid (`analyzer`) |
| `GET /v1/documents/{id}/analyses` | every score the CV got, across grid versions and analyzers |
| `POST /v1/documents/{id}/highlights` | highlight a passage: the `quote` selected in the PDF and its `page`, `start` and `end` in the text, or a `line`; `points` −100 to +100 (not 0, each passage once), `author_ref`, `comment`, and the selection's `boxes` to draw it back |
| `GET /v1/documents/{id}/highlights` | the passages highlighted, with their boxes on the PDF |
| `DELETE /v1/highlights/{id}` | remove one |
| `GET /v1/documents/{id}/score` | auto, manual and total points, with every point explained |
| `GET /v1/analyzers` | the analyzers and their versions |

### Webhooks

Set `WEBHOOKS=client:url` and the engine POSTs `{"event": ..., "data": ...}`
to that URL:

- `document.processed`: `document_id`, `external_ref`, `offer_ref`, `status`
- `analysis.done`: `document_id`, `external_ref`, `offer_ref`, `grid_version`, `analyzer`, `score`

With `WEBHOOK_SECRET` set, each call carries
`X-CVA-Signature: sha256=<HMAC-SHA256 of the body>`. Delivery is best
effort; the state can always be read with GET.

## Plugging it into RecruteHub

RecruteHub runs it like Code Playground: two more containers built from this
repository, a `cva_db` database in its Postgres and a bucket in its S3.

```yaml
  cva-api:
    build: { context: "https://github.com/Jmailachref/cv-analyzer.git", target: api }
    environment: &cva-env
      DATABASE_URL: postgresql+psycopg://cva:cva@postgres:5432/cva_db
      REDIS_URL: redis://redis:6379/0
      QUEUE_NAME: cva:jobs
      API_KEYS: recrutehub:${CVA_API_KEY:-recrutehub-dev-key}
      WEBHOOKS: recrutehub:http://candidates:8000/internal/cv-events
      STORAGE: s3
      S3_URL: http://s3:8333
      S3_ACCESS_KEY: recrutehub
      S3_SECRET_KEY: recrutehub-dev
      S3_BUCKET: cv-analyzer
  cva-worker:
    build: { context: "https://github.com/Jmailachref/cv-analyzer.git", target: worker }
    environment: *cva-env
```

The mapping:

| RecruteHub | CV Analyzer |
|---|---|
| job offer (`job_offers`) | `PUT /v1/offers/{offer id}` with its `title` and `skills` (`language`, `priority`), each time the offer is saved |
| offer deleted | `DELETE /v1/offers/{offer id}` |
| candidate id | `external_ref`; the apply page sends the PDF to `POST /v1/documents` with `offer_ref` = the offer id, and keeps the returned id |
| recruiter user id | `author_ref` on highlights |
| candidate list | `GET /v1/offers/{offer id}/ranking` |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://cva:cva@localhost:5432/cva` | Postgres |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis |
| `QUEUE_NAME` | `cva:jobs` | the Redis list jobs go through |
| `API_KEYS` | `dev:dev-key` | `client:key,client:key` |
| `OPEN_CLIENT` | empty | requests without an API key act as this client (local use; compose sets `dev`) |
| `WEBHOOKS` | empty | `client:url,client:url` |
| `WEBHOOK_SECRET` | empty | signs webhook bodies |
| `STORAGE` | `local` | `s3` or `local` |
| `STORAGE_DIR` | `data/files` | folder for `local` |
| `S3_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | bucket `cv-analyzer` | for `s3` |
| `MAX_PDF_MB` | `10` | largest PDF accepted |
| `OCR_LANGUAGES` | `fra+eng` | Tesseract languages |

## Tests

They need Postgres and Redis (the compose services, or any) and, for the OCR
test, Tesseract (`apt install tesseract-ocr tesseract-ocr-fra`).

```sh
pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg://cva:cva@localhost:5432/cva_test python -m pytest -q
cd web && npm ci && npm run build   # typecheck and build the web app
```

## Adding an analyzer

An analyzer takes the CV's lines, its offer's grid criteria, and returns
its points with their details (`analysis/analyzers.py`). Register it in
`ANALYZERS` and it is available through `POST /v1/documents/{id}/analyses`
with `"analyzer": "<name>"`, beside the keyword one, so the two can be
compared on the same CVs before switching. Planned: `embeddings` (a local
NLP model that also recognises skills the synonym list does not know) and,
later, `llm`.

## Layout

```
api/          FastAPI app: routes, schemas, API keys; serves web/dist under /app
core/         settings, database, models, queue, PDF storage, webhooks
analysis/     PDF extraction and OCR, text matching, synonyms, analyzers, total points
worker/       the queue worker
web/          the web app: React, TypeScript, Tailwind, pdf.js
migrations/   Alembic
tests/
```
