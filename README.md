# MarkovLotto - He Thong Thu Thap & Du Doan Xo So Sieu Toc 5 Phut

> **CANH BAO**: Day la cong cu ho tro nghien cuu hoc thuat. Chung toi khong chiu trach nhiem cho bat ky hanh vi loi dung nao tu phia nguoi dung.

`MarkovLotto` la he thong phan tich xac suat xo so thoi gian thuc, ket hop **Heuristics da lop** va **Gemini AI** de du doan ket qua Tai/Xiu, Chan/Le cho ky ke tiep, cung cap **quan ly von thong minh** va **cuoc gia lap** theo doi hieu suat.

---

## Cong Nghe Su Dung

| Thanh phan | Cong nghe |
|---|---|
| Backend | Python 3.10+, FastAPI |
| Web Server | Uvicorn |
| Giao thuc realtime | WebSocket (websockets) |
| Tinh toan | Pandas, NumPy |
| AI | Google Gemini API (gemini-2.5-flash) |
| Luu tru | In-Memory RAM / Redis (tuy cau hinh) |
| Frontend | HTML + Vanilla JS + CSS |

---

## Cau Truc Thu Muc

```
src/
  main.py                   # Khoi tao FastAPI, lifecycle, static files
  config.py                 # Cau hinh tu .env
  core/
    scraper.py              # WebSocket scraper + HTTP auto-fetch
    analyzer.py             # Toan bo logic phan tich & du doan (Combined Engine)
    gemini_client.py        # Giao tiep Gemini API (cache, rate-limit, retry)
    money_management.py     # Quan ly von (6 chien thuat)
  database/
    store.py                # DataStore (ke thua 3 Mixin)
    mixins/
      records_mixin.py      # Lich su ky quay
      predictions_mixin.py  # Du doan, thong ke, market health
      bets_mixin.py         # Balance, demo bet, loss streak
  api/
    routes.py               # Gop router vao prefix /api
    routers/
      core.py               # /history, /statistics, /mock-draw
      balance.py            # /balance, /demo-bet, /export/demo-bets
      analysis.py           # /predictions, /export/...
      config_routes.py      # /config-token, /config-fetch, /config-lottery
      script.py             # /script
  views/
    index.html              # Dashboard giao dien nguoi dung
    app.js                  # Frontend logic
    style.css               # CSS
```

---

## Huong Dan Cai Dat & Khoi Chay

### Cach 1: Scripts tu dong (Windows)

```bat
scripts\setup.bat           # Cai dat moi truong ao va thu vien
scripts\run.bat             # Khoi chay server
scripts\test.bat            # Chay unit tests
```

### Cach 2: Thu cong

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:PYTHONPATH="."; .venv\Scripts\python src/main.py
```

Dashboard: http://localhost:8000  
Swagger UI: http://localhost:8000/docs

### Cach 3: Docker Compose (Redis ben vung)

```bash
scripts\deploy_docker.bat            # Windows
./scripts/deploy_docker.sh           # Linux/macOS
```

---

## Bien Moi Truong (.env)

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

## Quy Trinh Van Hanh

### Buoc 1: Cap nhat Token WebSocket
1. Dang nhap tai https://vip.ee8833.me
2. F12 > Network > WS > chon ket noi /ws/
3. Sao chep gia tri token=... trong URL
4. Goi POST /api/config-token va dan token vao

### Buoc 2: Bootstrap du lieu lich su
- He thong tu dong fetch lich su khi khoi dong (_bootstrap_history)
- De nap thu cong: goi POST /api/import-history va dan JSON tu Network tab

### Buoc 3: Xem Dashboard
Truy cap http://localhost:8000:
- Trang thai ket noi WebSocket realtime
- Thong ke xac suat va du doan ky toi
- Lich su du doan + win/lose
- Nhat ky cuoc gia lap + quan ly von

---

## Logic Phan Tich & Du Doan (Core Engine)

### 1. Thu thap du lieu (scraper.py)

WebSocketScraper gom 2 vong lap song song (asyncio):

| Vong lap | Mo ta |
|---|---|
| _loop() | Ket noi WS, nhan ket qua moi ky quay realtime |
| _fetch_loop() | HTTP polling dinh ky (AUTO_FETCH_INTERVAL giay) fallback/bootstrap |

- Tu dong reconnect toi da 3 lan khi mat ket noi
- Ghi log trang thai: connected / reconnecting / disconnected

### 2. Phan tich thong ke - ProbabilityAnalyzer.analyze()

#### 2a. Thong ke co ban
- Tan suat Chan/Le, Tai/Xiu tren toan bo lich su
- Xac suat truot (sliding window N_sliding = 12-22 ky)
- Chuoi bet hien tai va Streak Transitions

#### 2b. Markov Chain cap 2
- Ma tran chuyen trang thai 4-trang thai (LL/LC/CL/CC)
- Yeu cau toi thieu 15 ky

#### 2c. Heuristics 3 lop (khong can Gemini API)

| Tang | Mo ta |
|---|---|
| Ping-Pong (AR) | Phat hien tin hieu dan xen (Alternation Rate) dung EMA lam tron. Khi AR >= nguong dong va xac nhan 2/3 ky gan nhat -> du doan doi chieu |
| Saturation | Sliding window 100 diem, tinh phan vi 50-60% de xac dinh nguong mua dong |
| Cooling-off / Win-streak | Tu dong BO QUA neu thua >= 3 ky lien tiep hoac thang >= 3 ky lien tiep |

Bo loc bo sung:
- Cross-market filter: Bat Chan 6 ky ma chon MUA TAI -> giam confidence 15
- Bet filter 7 ky: Bet >= 7 ky lien tiep -> dao chieu bat buoc
- Win rate filter: Bo qua neu win rate 15 ky < 50%
- MA-50 trend filter: Kiem tra xu huong dai han 50 ky
- Streak Safety Trap: Gioi han chuoi bet = max lich su + 2

#### 2d. Gemini AI Engine (gemini_client.py)

- Gui 100 ky lich su + boi canh (streak, Markov) toi gemini-2.5-flash
- Nhan JSON: {parity: {decision, confidence, rationale}, size: {...}}
- Cache theo ky quay (TTL = 300 giay), tranh goi API trung
- Retry toi da 3 lan voi exponential backoff (2s, 4s, 8s) khi 429

#### 2e. Combined Engine - Tong hop ket qua

| Truong hop | Ket qua | Engine |
|---|---|---|
| Gemini = Heuristics | Dong thuan, tang confidence +5 | Combined |
| Chenh lech >= 10% | Chon ben confidence cao hon | Gemini / Heuristics |
| Chenh lech < 10%, mau thuan | BO QUA bao toan | Conflict |
| Gemini khong kha dung | Heuristics tu dong thuan | Combined / Heuristics |

Kich hoat tang cuoc khi Combined:
- Engine = Combined, Confidence >= 70, XS truot >= 62%
- Tang 30% (conf 70-79), 35% (conf 80-89), 40% (conf 90-100)
- Gioi han toi da: max_bet_amount (cau hinh)

---

## Quan Ly Von (money_management.py)

### 6 chien thuat

| ID | Ten | Mo ta |
|---|---|---|
| fixed | Co dinh | Dat cung mot muc tien moi ky |
| martingale_x3 | Martingale x3 | Nhan 3 sau moi lan thua |
| fixed_fractional_3 | Fixed Fractional 3% | Dat 3% von hien tai moi ky |
| kelly_third | Kelly 1/3 | Kelly fraction / 3 (~5.3% von) |
| kelly_half_stoploss | Kelly 1/2 + Stop-loss | Kelly / 2, dung 24h sau 3 thua/ngay |
| kelly_half_martingale_x3 | **Toi uu** Dynamic Kelly & Martingale | Kelly dong theo WR + Martingale x3 giai doan dau |

### Dynamic Kelly & Martingale (chien thuat toi uu)
- Giai doan khoi tao (10 ky dau): Martingale x3, base 2% von, max 3 lan nhan
- Sau khoi tao, base % theo WR thuc te:
  - WR < 50%: 1.5% von
  - WR 50-55%: 3% von
  - WR 55-60%: 6% von (Kelly 1/3)
  - WR >= 60%: 10% von (Kelly 1/2)

### Kelly Stop-loss
- Ngung dat 24h khi thua >= 3 ky trong ngay (KELLY_HALF_STOPLOSS_DAILY_LIMIT = 3)
- Payout mac dinh: 0.95

---

## Cuoc Gia Lap (Demo Bets)

- So du mac dinh: 10,000,000 VND
- Luu toi da 100 ky gan nhat
- Ghi nhan: ky quay, cua dat, luong cuoc, ket qua, trang thai (win/lose/pending), engine (Gemini/Heuristics/Combined)
- Xuat CSV day du cot bao gom cot Thuat toan
- Thong ke loi nhuan rong realtime canh nut XUAT EXCEL: "Loi nhuan: +450,000 VND"

---

## Lich Su Du Doan

- Luu moi ky: du doan Parity, Size, engine, trang thai (win/lose/ignored)
- Hien thi engine kem theo: vi du "Chan (Combined)", "Tai (Gemini)"
- Luu toi da 100 ky gan nhat

---

## API Endpoints

### Core
| Method | Endpoint | Mo ta |
|---|---|---|
| GET | /api/history | Lich su ky quay (?limit=100) |
| GET | /api/statistics | Thong ke xac suat + du doan ky toi |
| POST | /api/mock-draw | Nhap thu cong ket qua ky quay |

### Cau hinh
| Method | Endpoint | Mo ta |
|---|---|---|
| POST | /api/config-token | Cap nhat token WebSocket |
| POST | /api/config-fetch | Cap nhat URL HTTP auto-fetch & interval |
| POST | /api/config-lottery | Thay doi loai xo so |

### So du & Cuoc
| Method | Endpoint | Mo ta |
|---|---|---|
| GET | /api/balance | So du, cau hinh cuoc, nhat ky (phan trang) |
| POST | /api/demo-bet | Cap nhat cau hinh cuoc |
| GET | /api/export/demo-bets | Xuat CSV nhat ky cuoc gia lap |

### Phan tich
| Method | Endpoint | Mo ta |
|---|---|---|
| GET | /api/predictions | Lich su du doan (?limit=100) |
| GET | /api/export/predictions | Xuat CSV lich su du doan |

---

## Luu Tru Du Lieu

| Che do | Kich hoat | Dac diem |
|---|---|---|
| RAM (mac dinh) | Chay local khong co Redis | Nhanh, mat du lieu khi tat server |
| Redis | Dat REDIS_HOST trong .env | Ben vung, ho tro deployment |

DataStore ke thua 3 Mixin:
- RecordsMixin: Lich su ky quay
- PredictionsMixin: Du doan, thong ke win/lose, market health
- BetsMixin: Balance, demo bet, loss streak, daily stop-loss

---

## Kiem Thu

```bash
.venv\Scripts\python -m pytest tests/ -v
```

---

## Luu Y Quan Trong

1. Du lieu toi thieu: Markov >= 10 ky, Heuristics tot nhat >= 50 ky.
2. Token WebSocket het han, can cap nhat thu cong qua POST /api/config-token.
3. RAM mode: Tat server mat du lieu. Dung Redis de ben vung.
4. Confidence toi da: He thong cap cung o 70% tranh over-confidence.
5. Muc dich nghien cuu hoc thuat, khong phai loi khuyen dat cuoc thuc te.
