# MarkovLotto - Real-Time Ultra-Fast 5-Minute Lottery Analysis & Prediction System

> **DISCLAIMER**: This tool is designed strictly for academic research and educational purposes. The developers accept no responsibility or liability for any misuse or actions taken by users.

`MarkovLotto` is a real-time lottery probability analysis system that combines **multi-layer heuristics** and **Google Gemini AI** to predict Big/Small (Tai/Xiu) and Odd/Even (Chan/Le) outcomes for upcoming draws. It features **intelligent capital management strategies** and a **simulated betting engine** to track performance metrics.

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI |
| Web Server | Uvicorn |
| Real-time Protocol | WebSocket (`websockets`) |
| Data Processing | Pandas, NumPy |
| AI Engine | Google Gemini API (`gemini-2.5-flash`) |
| Data Storage | In-Memory RAM / Redis (configurable) |
| Frontend | HTML + Vanilla JS + CSS |

---

## Directory Structure

```text
src/
  main.py                 # FastAPI initialization, lifecycle management, static files
  config.py               # Configuration management via .env
  core/
    scraper.py            # Real-time WebSocket scraper + HTTP auto-fetch fallback
    analyzer.py           # Core analysis and prediction logic (Combined Engine)
    gemini_client.py      # Gemini API interface (caching, rate limiting, retry mechanism)
    money_management.py   # Capital management engine (6 strategies)
  database/
    store.py              # Main DataStore (inherits from 3 Mixins)
    mixins/
      records_mixin.py    # Draw history records
      predictions_mixin.py# Predictions, win/loss stats, market health indicators
      bets_mixin.py       # Account balance, demo betting, loss streak tracking
  api/
    routes.py             # Main router aggregator under the /api prefix
    routers/
      core.py             # /history, /statistics, /mock-draw
      balance.py          # /balance, /demo-bet, /export/demo-bets
      analysis.py         # /predictions, /export/...
      config_routes.py    # /config-token, /config-fetch, /config-lottery
      script.py           # /script
  views/
    index.html            # User Dashboard UI
    app.js                # Frontend application logic
    style.css             # UI Styling
```

---

## Installation & Setup Guide

### Option 1: Automated Scripts (Windows)

```bat
scripts\setup.bat           # Set up virtual environment and install dependencies
scripts\run.bat             # Launch the application server
scripts\test.bat            # Execute unit tests
```

### Option 2: Manual Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:PYTHONPATH="."; .venv\Scripts\python src/main.py
```

* **Dashboard**: `http://localhost:8000`
* **Swagger API Docs**: `http://localhost:8000/docs`

### Option 3: Docker Compose (Persistent Redis)

```bash
# On Windows:
scripts\deploy_docker.bat

# On Linux / macOS:
./scripts/deploy_docker.sh
```

---

## Environment Variables (`.env`)

```env
GEMINI_API_KEY=your_google_gemini_api_key
TARGET_WS_URL=wss://vip.ee8833.me/ws/?token=...
TARGET_DOMAIN=vip.ee8833.me
LOTTERY_ID=45
LOTTERY_CODE=pmb5p
GEMINI_MODEL=gemini-2.5-flash
GEMINI_API_VERSION=v1beta
API_HOST=0.0.0.0
API_PORT=8000
MAX_HISTORY_SIZE=10000
DRAWS_RESULT_URL=https://...
AUTO_FETCH_INTERVAL=60
REDIS_HOST=
REDIS_PORT=6379
REDIS_PASSWORD=
```

---

## Operational Workflow

### Step 1: Update WebSocket Token
1. Log in to your target platform (e.g., `https://vip.ee8833.me`).
2. Open Developer Tools (`F12`) > **Network** > **WS** tab > Select the `/ws/` connection.
3. Copy the `token=...` query parameter value from the request URL.
4. Issue a `POST /api/config-token` request containing your extracted token.

### Step 2: Bootstrap Historical Data
* The system automatically fetches draw history on startup (`_bootstrap_history`).
* To trigger a manual import: Send a `POST /api/import-history` payload containing raw JSON copied from the Network tab.

### Step 3: Access the Dashboard
Navigate to `http://localhost:8000` to monitor:
* Real-time WebSocket connection status.
* Statistical probabilities and predictions for the upcoming draw.
* Prediction history alongside win/loss tracking.
* Simulated betting logs and active money management metrics.

---

## Analysis & Prediction Architecture (Core Engine)

### 1. Data Collection (`scraper.py`)

The `WebSocketScraper` operates via two concurrent asynchronous tasks (`asyncio`):

| Task Loop | Description |
|---|---|
| `_loop()` | Maintains WebSocket connection to ingest incoming draw results in real time. |
| `_fetch_loop()` | Executes periodic HTTP polling (`AUTO_FETCH_INTERVAL`) as a fail-safe fallback and bootstrapper. |

* Automatic reconnection strategy with up to 3 retries on network drops.
* Real-time connection status logging: `connected` / `reconnecting` / `disconnected`.

---

### 2. Statistical Analysis — `ProbabilityAnalyzer.analyze()`

#### 2a. Base Statistics
* Overall historical frequencies for Odd/Even and Big/Small.
* Sliding window probability calculations ($N_{\text{sliding}} = 12 \text{ to } 22$ draws).
* Current streak tracking and Streak Transition matrices.

#### 2b. 2nd-Order Markov Chain
* Evaluates a 4-state transition matrix (`Even-Even`, `Even-Odd`, `Odd-Even`, `Odd-Odd`).
* Requires a minimum threshold of 15 historical draws.

#### 2c. 3-Layer Heuristics (Standalone — No API Required)

| Layer | Function |
|---|---|
| **Ping-Pong (AR)** | Detects alternating patterns via exponential moving average (EMA) smoothed Alternation Rate (AR). Triggers counter-trend predictions when AR exceeds dynamic thresholds and receives validation across 2/3 recent draws. |
| **Saturation** | Calculates 50–60th percentiles over a 100-sample sliding window to evaluate overbought/oversold boundaries. |
| **Cooling-Off / Win-Streak** | Forces a **SKIP** signal when experiencing $\ge 3$ consecutive wins or losses to prevent over-trading during anomalous streaks. |

**Additional Safeguards & Filters:**
* **Cross-Market Filter**: Reduces confidence by 15% when contradictory signals occur across markets (e.g., Even streak of 6 triggers Big prediction).
* **7-Draw Bet Filter**: Reverses direction automatically when a pattern persists for $\ge 7$ consecutive draws.
* **Win Rate Filter**: Skips prediction if the 15-draw rolling win rate drops below 50%.
* **MA-50 Trend Filter**: Assesses macro-level direction using a 50-draw moving average.
* **Streak Safety Trap**: Caps allowable streaks at `historical_max + 2`.

---

#### 2d. Gemini AI Engine (`gemini_client.py`)

* Formats a prompt with the past 100 historical draws alongside contextual metadata (streaks, Markov metrics) for `gemini-2.5-flash`.
* Returns structured JSON: `{parity: {decision, confidence, rationale}, size: {...}}`.
* Features per-draw caching (TTL = 300s) to prevent redundant API calls.
* Retries up to 3 times with exponential backoff (2s, 4s, 8s) upon encountering HTTP 429 rate limits.

---

#### 2e. Combined Engine — Consensus Aggregation

| Condition | Action / Output | Engine Label |
|---|---|---|
| Gemini matches Heuristics | High consensus: increases confidence by +5%. | `Combined` |
| Confidence Delta $\ge 10\%$ | Chooses direction with the higher confidence score. | `Gemini` / `Heuristics` |
| Confidence Delta $< 10\%$ with conflicting outputs | Outputs **SKIP** signal to preserve capital. | `Conflict` |
| Gemini API unavailable | Falls back seamlessly to Heuristics output. | `Combined` / `Heuristics` |

**Dynamic Stake Amplification:**
* Activated when: `Engine == Combined`, `Confidence >= 70%`, and `Sliding Window Win Prob >= 62%`.
* Stake increases: +30% (Confidence 70–79%), +35% (Confidence 80–89%), +40% (Confidence 90–100%).
* Bound by `max_bet_amount` configuration.

---

## Money Management (`money_management.py`)

### 6 Available Strategies

| Strategy ID | Name | Description |
|---|---|---|
| `fixed` | Fixed Amount | Places an identical flat stake on every draw. |
| `martingale_x3` | Martingale 3x | Triples the previous bet size following a loss. |
| `fixed_fractional_3` | Fixed Fractional 3% | Stakes 3% of current account balance on each draw. |
| `kelly_third` | Fractional Kelly (1/3) | Applies $1/3$ Kelly Criterion (~5.3% of balance). |
| `kelly_half_stoploss` | Kelly 1/2 + Stop-Loss | Applies $1/2$ Kelly Criterion; halts betting for 24h after 3 daily losses. |
| `kelly_half_martingale_x3` | **Optimal** Dynamic Kelly & Martingale | Combines dynamic Kelly scaling based on Win Rate with early-stage Martingale 3x. |

### Dynamic Kelly & Martingale Algorithm
* **Warm-up Phase (First 10 draws)**: Martingale 3x starting from 2% base balance, capped at 3 consecutive multipliers.
* **Post Warm-up Phase**: Base stake scales according to actual rolling win rate:
  * Win Rate $< 50\%$: 1.5% balance
  * Win Rate $50–55\%$: 3% balance
  * Win Rate $55–60\%$: 6% balance ($1/3$ Kelly)
  * Win Rate $\ge 60\%$: 10% balance ($1/2$ Kelly)

### Risk Mitigation & Stop-Loss
* **Daily Circuit Breaker**: Suspends betting for 24 hours if consecutive daily losses reach 3 (`KELLY_HALF_STOPLOSS_DAILY_LIMIT = 3`).
* **Default Payout Ratio**: Configured at 0.95.

---

## Simulated Betting Engine (Demo Bets)

* **Default Starting Balance**: 10,000,000 VND
* **History Buffer**: Retains up to 100 recent draws.
* **Recorded Fields**: Draw ID, target selection, stake amount, outcome, status (`win`/`loss`/`pending`), and executing engine (`Gemini`/`Heuristics`/`Combined`).
* **Export**: Full CSV export capabilities including Algorithm metadata columns.
* **Real-time Profit Display**: Dynamic profit metric displayed alongside export buttons (e.g., `"Net Profit: +450,000 VND"`).

---

## API Reference

### Core Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/history` | Fetches historical draw records (`?limit=100`). |
| `GET` | `/api/statistics` | Returns current statistical metrics and next-draw prediction. |
| `POST` | `/api/mock-draw` | Manually injects a draw result for testing. |

### Configuration Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/config-token` | Updates active WebSocket authentication token. |
| `POST` | `/api/config-fetch` | Configures HTTP auto-fetch target URL and polling interval. |
| `POST` | `/api/config-lottery` | Updates target lottery type parameters. |

### Balance & Betting Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/balance` | Returns balance details, betting parameters, and paginated logs. |
| `POST` | `/api/demo-bet` | Updates mock betting engine configuration. |
| `GET` | `/api/export/demo-bets` | Exports mock betting history to CSV. |

### Analysis & Prediction Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/predictions` | Fetches recent prediction logs (`?limit=100`). |
| `GET` | `/api/export/predictions` | Exports prediction history to CSV format. |

---

## Recent Logic & Algorithmic Improvements

### 1. Core Analyzer Optimizations & Bug Fixes
* **Sliding Window Boundary Calculation**: Resolved an issue where probability calculations were skewed when available historical draws were less than window size $N$ (`len(history) < N`). The algorithm now dynamically scales to `actual_n`, guaranteeing 100% calculation accuracy from initial draws.
* **Sawtooth Strategy (AR-based Ping-Pong)**: Refactored Layer 1 to prioritize 1-1 alternating patterns when `ar_smooth` exceeds `ar_threshold`, enabling automatic transition into trend-following mode if the alternating pattern breaks.

### 2. Persistence & Config Presets
* **Database Schema Support (PostgreSQL / SQLite / Redis)**:
  * `predictions`: Logs prediction history (Draw ID, Side, Confidence, Rationale, Win/Loss status).
  * `bets`: Records execution logs for mock bets.
  * `ai_audit_logs`: Maintains audit trails for calls made to the Gemini API.
* **Configuration Preset Management**: Supports persistent saving, loading, and dynamic switching of parameter presets stored in PostgreSQL or Redis.

---

## Data Storage Modes

| Mode | Trigger Condition | Characteristics |
|---|---|---|
| **RAM (Default)** | Local deployment without Redis | High throughput; data resets on process restart. |
| **Redis** | `REDIS_HOST` configured in `.env` | Persistent; production-grade multi-worker support. |

The main `DataStore` class aggregates three Mixins:
* `RecordsMixin`: Historical draw data.
* `PredictionsMixin`: Predictions, win/loss stats, and market health monitoring.
* `BetsMixin`: Balance management, demo bet processing, loss streaks, and daily stop-loss tracking.

---

## Running Tests

Execute unit tests via `pytest`:

```bash
.venv\Scripts\python -m pytest tests/ -v
```

---

## Technical Notes

1. **Minimum Historical Data**: Requires $\ge 10$ draws for Markov chain execution; optimal Heuristics performance requires $\ge 50$ draws.
2. **Token Expiration**: WebSocket tokens expire periodically; update them via `POST /api/config-token`.
3. **RAM Mode Data Persistence**: Data is volatile in RAM mode; switch to Redis for persistent workloads.
4. **Confidence Ceiling**: System confidence scores are capped at 70% to prevent over-confidence bias.
5. **Academic Scope**: Intended purely for computational research and statistical modeling.