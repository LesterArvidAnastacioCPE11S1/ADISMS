# ADISMS — Arvid DryGoods Inventory and Sales Management System

Web-based inventory, sales, and delivery system with three product-identification
methods (manual search, barcode lookup, and image recognition). This is the
implementation for the Group 7 capstone design project.

## Folder structure

```
ADISMS/
├── run.py                     # start the web app (python run.py)
├── start.bat                  # Windows one-click setup + start (+ --test, --cnn, --lan)
├── requirements.txt
├── .gitignore
├── app/
│   ├── __init__.py            # application factory, index route, error handlers
│   ├── config.py              # paths, thresholds, targets (env-overridable)
│   ├── database.py            # SQLite schema + stock/ACID operations + reports
│   ├── db_session.py          # one connection per request
│   ├── auth.py                # owner sign-up, login, settings, staff accounts, guards
│   ├── api.py                 # JSON API (dashboard, products, sales, reports, recognition)
│   ├── recognition/
│   │   ├── __init__.py        # engine registry: template | orb | cnn | auto
│   │   ├── base.py            # Match / Candidate / RecognitionError
│   │   ├── dataset.py         # reference-image index from data/products/<id>/
│   │   ├── imaging.py         # OpenCV decode/resize helpers
│   │   ├── template.py        # Alternative A — template matching
│   │   ├── orb.py             # Alternative B — ORB feature matching
│   │   ├── cnn.py             # Alternative C — MobileNetV3 transfer learning
│   │   └── evaluate.py        # held-out accuracy + response-time harness
│   └── static/
│       ├── index.html
│       ├── css/style.css      # cream/green mobile design system
│       ├── js/app.js          # SPA: login, home, inventory, scan, cart, receipt, stock, delivery, register, sales, settings, staff, activity log
│       └── img/store-shelves.jpg  # identify-screen backdrop
├── ml/
│   ├── train_cnn.py           # train data/models/cnn.pt (PyTorch + torchvision)
│   └── split_dataset.py       # move a share of photos into the held-out test set
├── tools/
│   ├── evaluate_recognition.py   # prints the Chapter 3 comparison table
│   └── make_demo_dataset.py      # synthetic demo photos (mock data only)
├── tests/
│   ├── helpers.py             # synthetic images for deterministic tests
│   ├── test_stock.py          # ACID stock updates + 100 random transactions
│   ├── test_api.py            # API, uploads, recognition endpoint
│   ├── test_auth.py           # owner sign-up, login, settings, staff accounts, migration
│   ├── test_cart_reports.py   # cart sales, delivery metadata, stock/report APIs, migration
│   └── test_recognition.py    # engines + evaluation harness
├── data/
│   ├── products/<product_id>/*.jpg   # reference photos + CNN training photos
│   ├── test/<product_id>/*.jpg       # held-out evaluation photos
│   ├── models/                       # cnn.pt + class_map.json
│   └── eval/                         # evaluation result JSON
└── adisms.db                  # SQLite database (created on first run)
```

## Setup and run

```bash
cd ADISMS
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt  # torch is only needed for Alternative C
python run.py
```

### Quick start on Windows

Double-click `start.bat` (or run it from Command Prompt). On first run it creates
`.venv`, installs the core dependencies, creates a local `.secret_key`, starts the
server, and opens <http://127.0.0.1:5000>.

```bat
start.bat               :: set up if needed, start, open the browser
start.bat --no-browser  :: start without opening the browser
start.bat --cnn         :: also install PyTorch for recognition alternative C
start.bat --test        :: run the test suite and exit
start.bat --lan         :: also accept phones/tablets on the same Wi-Fi
```

Open <http://127.0.0.1:5000>. The app starts with **no accounts and no
products**: the login page and the sign-up page ("Create the owner account")
are both always available.

**First run:** open the sign-up page, create the Owner account (username,
email, optional phone, password), then you are returned to the login page and
**sign in with those same credentials**. Sign-up does not start a session.
Once an Owner exists, the sign-up endpoint refuses further registrations; all
later accounts are created by the Owner from **Settings → Staff accounts**
(Owner only). Choose a username, a valid email, an optional phone number, and
an 8-character password. Employees can record sales and deliveries but cannot
manage products, staff, or reports. You can log in with either the username or
the email; email and phone can be changed later from **Settings**, which also
lets the signed-in user change their password. Existing databases are upgraded
in place: the `email`, `phone`, and `created_at` columns are added without
deleting accounts.

No accounts or products are seeded, so everything you see is data you entered.
Databases created by older builds may still contain sample `owner`/`employee`
accounts; they are not removed automatically — back up `adisms.db` and remove
them if you want a clean start. The owner can review every sign-in, failed
sign-in, sale, delivery, product change, and account change in
**Settings → Activity log**, which is never shown to employees.

### Using it on phones and other devices

The server binds to `127.0.0.1` (this PC only) by default. Start it with
`start.bat --lan` or set `ADISMS_HOST=0.0.0.0` before `python run.py`, then open
`http://<this-pc-ip>:5000` on the other device (same Wi-Fi network). Allow the
Windows firewall prompt for private networks. `ADISMS_PORT` changes the port
and `ADISMS_DEBUG=1` enables the Flask debugger. Set `ADISMS_SECRET_KEY` (and
`ADISMS_DB`, `ADISMS_DATA_DIR` if needed) in the environment for anything
beyond local testing — without a fixed key every restart invalidates sessions.

## Screens

The interface is a single-page mobile layout (max 440 px) with four bottom tabs
— **Home**, **Inventory**, **Stock**, **Sales** — plus focused screens:

| Screen | What it does |
|---|---|
| Sign in | username/email + password; link to the sign-up page |
| Owner sign-up | creates the lone Owner account, then returns to Sign in (no auto-login) |
| Home | today's sales, transactions, items sold, product count, hourly chart, quick actions, stock attention |
| Inventory | search by name/ID, stock filter, sort, product cards, Add product |
| Product details | photo, price, stock, reorder level, stock-movement history, recognition-photo upload, Delete product (owner only) |
| Identify product | dark camera screen: barcode or photo; engine picker; manual search fallback |
| Check the product | confirms the match with confidence and response time before anything changes |
| New sale | search/browse items, multi-product cart with steppers, one atomic sale |
| Receipt | sale number, lines, total, per-line stock before → after |
| Stock | out-of-stock/low-stock summary, lowest quantities first, Receive stock |
| Receive delivery | quantity, date received, delivery reference, stock-after preview |
| Register product | photo, name, ID, price, initial stock, reorder level, barcode |
| Daily sales | date navigation, totals, hourly chart, top products, recent sales |
| Settings | email/phone, password change, Staff accounts and Activity log (owner only), log out |
| Staff accounts | owner-only: list of accounts, create employee accounts, recent stock activity |
| Activity log | owner-only audit trail of sign-ins, failed sign-ins, sales, deliveries, product changes and account changes |

Identifying a product never changes stock: stock is deducted only when a sale
is recorded and added only when a delivery is saved.

## How the objectives map to the code

| Objective | Where |
|---|---|
| 1. Architecture + UI | `app/__init__.py`, `app/static/` |
| 2. Central database + registration | `app/database.py`, `POST /api/products`, Register screen |
| 3. Manual search / barcode / image recognition | `GET /api/products?q=`, `GET /api/barcode/<code>`, `app/recognition/`, `POST /api/recognize` |
| 4. Auto stock updates + low-stock flags | `database._apply`, `database.low_stock`, stock checker on dashboard |
| 5. Daily sales + graphical reports | `database.daily_sales`, `database.top_products`, dashboard chart, Reports screen |
| 6. Testing and evaluation | `tests/`, `tools/evaluate_recognition.py` |

## Collecting the image dataset

1. Photograph every product to be recognized, 5–10 photos each, from different
   angles and lighting. Store at `data/products/<product_id>/<anything>.jpg`.
   Product IDs must match the database (letters, numbers, `-`, `_`, max 32).
   You can also upload photos from the product's Details screen.
2. Move 20–30% of each product's photos into the held-out set. **Training and
   reference images must not appear in the test set** or the accuracy is inflated:

   ```bash
   python ml/split_dataset.py --ratio 0.3
   ```

3. (Optional, Alternative C) train the CNN:

   ```bash
   python ml/train_cnn.py --data data/products --out data/models --epochs 12
   ```

4. Evaluate the alternatives (targets: ≥ 90% accuracy, mean ≤ 3 s):

   ```bash
   python tools/evaluate_recognition.py
   python tools/evaluate_recognition.py --engine template --limit 100
   ```

   Each run prints a Markdown table and saves `data/eval/eval_<engine>_<time>.json`
   with per-attempt results. Use the real-photo run for Chapter 3.

Do **not** report results from `tools/make_demo_dataset.py` as real performance.
Those images are synthetic; label them as mock/simulation data if used at all.
Delete them with `python tools/make_demo_dataset.py --clean` before collecting
real data.

## Recognition alternatives

| Engine | File | Method | Acceptance rule |
|---|---|---|---|
| `template` (A) | `app/recognition/template.py` | 224×224 grayscale templates + `TM_CCOEFF_NORMED` | score ≥ `ADISMS_TEMPLATE_THRESHOLD` (0.45) |
| `orb` (B) | `app/recognition/orb.py` | ORB descriptors + BFMatcher + Lowe ratio 0.75 | good matches ≥ `ADISMS_ORB_MIN_MATCHES` (12) |
| `cnn` (C) | `app/recognition/cnn.py` | MobileNetV3 transfer learning, softmax | probability ≥ `ADISMS_CNN_THRESHOLD` (0.60) |

`auto` uses the CNN when `data/models/cnn.pt` exists and PyTorch is installed;
otherwise it falls back to template matching. Tune thresholds on a validation
split, then document the final values and the measured accuracy/response time.

## API summary

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/register` | first-run owner sign-up; does not sign in (refused once an Owner exists) |
| GET | `/api/setup` | whether the Owner account still needs to be created |
| POST | `/api/login`, `/api/logout` | session auth (username or email + password) |
| GET | `/api/me` | current user |
| GET/POST | `/api/staff` | staff accounts + recent stock activity / create an Employee (Owner only) |
| GET | `/api/staff/logs?limit=100&action=` | Owner-only activity log (sign-ins, sales, deliveries, product/account changes) |
| GET/PATCH | `/api/settings` | read / update email and phone |
| POST | `/api/settings/password` | change password (requires current password) |
| GET | `/api/dashboard` | sales today, 7-day chart, low-stock list |
| GET | `/api/products?q=` | manual search by name / ID |
| GET | `/api/products/<id>` | product details |
| POST | `/api/products` | register product |
| DELETE | `/api/products/<id>` | remove a product and its photos (Owner only; blocked when sales/delivery history exists) |
| GET/POST | `/api/products/<id>/image(s)` | cover photo / upload recognition photos |
| GET | `/api/barcode/<code>` | barcode lookup |
| POST | `/api/sales`, `/api/deliveries` | single stock-changing transaction (deliveries accept `reference`, `received_on`) |
| POST | `/api/sales/cart` | multi-product sale as one atomic batch (items: `[{product_id, quantity}]`) |
| GET | `/api/stock` | out/low stock summary, attention list, remaining products |
| GET | `/api/reports/summary?days=7` | totals, chart, top products, ledger |
| GET | `/api/reports/day?date=YYYY-MM-DD` | one day's totals, hourly buckets, top products, recent sales |
| GET | `/api/transactions?limit=50` | inventory ledger |
| GET | `/api/recognition/engines` | availability of A/B/C |
| POST | `/api/recognize` | multipart `image` + `engine` → product + confidence + time |

## Tests

```bash
python -m unittest discover -s tests -t .
```

Covers stock arithmetic, negative-stock rejection, 100 random transactions
against an expected ledger, owner sign-up and the single-owner rule,
login/settings/password flows, owner-only staff creation and staff activity,
the owner-only activity log (including failed sign-ins and employee denial),
the legacy-database migration, uploads, the recognition endpoint, engine
ranking/rejection, the evaluation harness, atomic multi-product cart sales,
delivery date/reference validation, product stock movements, the stock and
daily-report endpoints, and product deletion rules (Owner only, history
protected, photos and barcodes cleaned up).

Older databases are upgraded in place on startup: accounts gain
`email`/`phone`/`created_at`, sales gain `batch_id` (each pre-cart sale becomes
its own batch), deliveries gain `reference`, and the supporting indexes are
created after the columns exist.

## Notes before deployment

- Set a real `ADISMS_SECRET_KEY`; the first sign-up creates the Owner account,
  so do it before exposing the server to anyone else.
- Serve over HTTPS if the phone and server are not on a trusted local network.
- The barcode camera scanner uses the browser's `BarcodeDetector` (Chrome/Edge
  on Android and desktop). Typing the number always works as a fallback.
- Back up `adisms.db` and the `data/products/` folder together; photos are not
  stored inside the database.
- The system does not order stock from suppliers automatically (a stated
  delimitation); it only flags low-stock products.
- Deleting a product is limited to the Owner role. Products that already have
  sales or delivery history are kept so past reports stay accurate; only
  products with no transactions can be removed.
