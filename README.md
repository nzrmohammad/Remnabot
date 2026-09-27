# 🚀 Remnabot — Enterprise Remnawave Telegram Bot

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/Framework-aiogram%203.31%2B-2C8EBB.svg?style=for-the-badge&logo=telegram" alt="aiogram 3.31+" />
  <img src="https://img.shields.io/badge/Panel-Remnawave%20v3%2B%20Only-8A2BE2.svg?style=for-the-badge" alt="Remnawave v3+ Only" />
  <img src="https://img.shields.io/badge/Database-PostgreSQL%2016%20%7C%20Redis-blueviolet.svg?style=for-the-badge&logo=postgresql" alt="PostgreSQL & Redis" />
  <img src="https://img.shields.io/badge/Architecture-AsyncIO%20%7C%20Zero--Conflict-success.svg?style=for-the-badge" alt="Zero-Conflict Architecture" />
  <img src="https://img.shields.io/badge/Channel-@Nzrmohammad-brightgreen.svg?style=for-the-badge&logo=telegram" alt="Telegram" />
</p>

<p align="center">
  <b>Enterprise-Grade, Asynchronous Telegram Automation & Client Portal exclusively engineered for Remnawave v3+ Panels.</b>
</p>

---

## 📖 Table of Contents
- [⚡ Key Features](#-key-features)
- [🏛 Project Architecture](#-project-architecture)
- [⚡ Zero-Conflict Deployment Model](#-zero-conflict-deployment-model)
- [📦 Prerequisites & Compatibility](#-prerequisites--compatibility)
- [🚀 Quick Start](#-quick-start)
- [🔄 Updating Guide](#-updating-guide)
- [💾 Migration & Server Relocation](#-migration--server-relocation)
- [⚙️ Configuration Guide (`.env`)](#-configuration-guide-env)
- [⏰ Background Schedulers & Lifecycle Engine](#-background-schedulers--lifecycle-engine)
- [🛠 Store & Operations Management](#-store--operations-management)
- [🗺 Project Roadmap](#-project-roadmap)
- [🧪 Testing & Quality Assurance](#-testing--quality-assurance)
- [👨‍💻 Community & License](#-community--license)

---

## ⚡ Key Features

Remnabot provides a production-grade Telegram client portal and administrative operations suite:

- **👤 Unified Client Hub**: Multi-subscription management under a single Telegram ID, one-step free trial provisioning, HWID device control, and persistent bilingual localization (English & Persian).
- **⚡ Live 1-Tap Single Configs**: Instant extraction of raw subscription payloads into distinct VLESS, Trojan, and Shadowsocks nodes with native 1-tap clipboard copy buttons (`CopyTextButton`).
- **💳 Financial & Wallet Integrity**: Card-to-card deposit processing with SHA-256 duplicate slip prevention, interactive review queues with instant push notifications, Telegram Supergroup Forum Topic routing, percentage/fixed discount coupons, and referral reward bonuses.
- **💎 Direct On-Chain Crypto Payments**: Native The Open Network (TON) cryptocurrency top-up with 1-tap Tonkeeper and Telegram Wallet deep-links (auto-filling address, TON amount, and memo), multi-source resilient real-time rate queries (Nobitex / Bitpin / Wallex or global Binance / TonAPI / CoinGecko fallback), and 4x daily rate notifications with 1-click update buttons.
- **👑 Autonomous Executive Reports**: Automated daily reports at 23:59 with country-level node bandwidth breakdowns, active user summaries, 3-day expiry alerts, and weekly top-20 rankings with daily champions.
- **🤖 Intelligent Lifecycle & Retention Engine**: Autonomous asynchronous workers handling proactive expiration warnings (3-Day, 1-Day, Day-0), grace period policy enforcement, auto-disabling expired panel subscriptions, and automated 7-day win-back retention campaigns.
- **📊 Real-Time Cluster Telemetry**: Proactive monitoring of all Remnawave v3 nodes with automated country flag resolution, core version detection (`Xray-core` / `Node`), hardware load metrics (CPU, RAM, Uptime), and real-time active user counts.
- **🐳 Zero-Conflict Production Architecture**: Outbound-only long-polling requiring zero exposed HTTP/SSL ports on the host, fully isolated PostgreSQL 16 and Redis 7 containers, and an automated native self-healing schema engine with zero manual migrations.

---

## 🏛 Project Architecture

Remnabot is engineered with a clean, decoupled layer architecture ensuring high concurrency, fault tolerance, and clear separation of concerns:

```text
remnawave-bot/
├── bot/
│   ├── db/                         # Data Layer: Async SQLAlchemy engine & repositories
│   │   ├── repositories/           # Isolated domain data access objects (12 specialized repos)
│   │   │   ├── admin_log_repo.py   # Administrative audit trails
│   │   │   ├── alert_repo.py       # Expiration & quota warning deduplication
│   │   │   ├── app_setting_repo.py # Dynamic in-bot runtime configurations
│   │   │   ├── coupon_repo.py      # Discount & promotional code management
│   │   │   ├── order_repo.py       # Purchase tracking & refund processing
│   │   │   ├── referral_repo.py    # Affiliate tracking & reward distribution
│   │   │   ├── user_repo.py        # User profile, balances, & blacklist state
│   │   │   └── wallet_repo.py      # Card-to-card deposit transactions & receipts
│   │   ├── base.py                 # Async sessionmaker & self-healing auto-migration engine
│   │   └── models.py               # Relational database schema models
│   ├── handlers/                   # Presentation Layer: Modular aiogram 3.31+ routers
│   │   ├── account.py              # Subscription manager & user dashboard
│   │   ├── admin.py                # Admin control panel, store settings, & broadcaster
│   │   ├── admin_ops.py            # Financial transaction approval & coupon operations
│   │   ├── admin_users.py          # User management, balance adjustments, & search
│   │   ├── configs.py              # 1-tap clipboard single-config extraction
│   │   ├── service_request.py      # Plan purchase & renewal workflows
│   │   ├── start.py                # Deep-link referral capture & onboarding
│   │   └── wallet.py               # Card-to-card top-up & receipt upload flows
│   ├── keyboards/                  # UI Components: Inline keyboard builders (RTL-aware)
│   ├── locales/                    # Bilingual localization dictionaries (Persian & English)
│   ├── middlewares/                # Processing Pipeline: Execution filters & hooks
│   │   ├── ban_check.py            # Global blacklist enforcement & drop filter
│   │   ├── db.py                   # Async database session lifecycle injection
│   │   └── rate_limit.py           # Anti-flood leaky bucket rate limiter
│   ├── services/                   # Domain Logic & Asynchronous Automation Workers
│   │   ├── remnawave.py            # Remnawave v3+ REST API client & cluster adapter
│   │   ├── backup.py               # Database snapshot creation & Telegram document dispatcher
│   │   ├── configs.py              # Subscription URI decoder & node parser
│   │   ├── expiry.py               # Expiration warnings & account deactivation
│   │   ├── formatting.py           # Jalali dates, traffic formatters, & visual progress bars
│   │   ├── reports.py              # Executive nightly, weekly, & monthly summaries (23:59)
│   │   ├── retention.py            # Automated customer win-back retention campaigns
│   │   └── topups.py               # Top-up decision workflows & smart routing
│   ├── states/                     # Finite State Machine (FSM) conversation groups
│   ├── config.py                   # Strongly-typed Pydantic v2 application settings
│   └── main.py                     # Bot entrypoint, router binding, & scheduler launcher
├── tests/                          # Comprehensive test suite (58 passing tests)
├── docker-compose.yml              # Production multi-container orchestration (Bot, DB, Redis)
├── Dockerfile                      # Optimized Python 3.12-slim multi-stage image
├── requirements.txt                # Pinned production dependencies
└── .env.example                    # Environment variable template
```

### Architectural Data Flow

```text
 ┌─────────────────┐       ┌────────────────────────┐       ┌───────────────────────┐
 │  Telegram API   │◄─────►│    remnawave-bot       │◄─────►│   Remnawave v3 Panel  │
 │ (Long-Polling)  │       │ (AsyncIO / aiogram 3)  │       │   (REST API v3+)      │
 └─────────────────┘       └───────────┬────────────┘       └───────────────────────┘
                                       │
                  ┌────────────────────┴────────────────────┐
                  ▼                                         ▼
      ┌───────────────────────┐                 ┌───────────────────────┐
      │  remnawave-bot-db     │                 │  remnawave-bot-redis  │
      │  (PostgreSQL 16)      │                 │  (Redis 7 Alpine)     │
      └───────────────────────┘                 └───────────────────────┘
```

---

## ⚡ Zero-Conflict Deployment Model

When hosting the bot on the same virtual server as **Remnawave v3**, the primary engineering concern is preventing **port collisions, database contention, and memory exhaustion**.

Remnabot solves this completely with a **Zero-Conflict Guarantee**:

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                              HOST SERVER                               │
 │                                                                        │
 │  ┌─────────────────────────┐             ┌──────────────────────────┐  │
 │  │ Remnawave v3 Panel      │             │ Web Reverse Proxy        │  │
 │  │ (Docker Container)      │             │ (Caddy / Nginx / Traefik)│  │
 │  │ Port 3000 (Internal)    │             │ Ports 80 & 443 (Host)    │  │
 │  └────────────▲────────────┘             └──────────────────────────┘  │
 │               │ REST API Communication                                 │
 │  ┌────────────┴─────────────────────────────────────────────────────┐  │
 │  │ Private Docker Bridge Network (`remnawave-bot-net`)              │  │
 │  │                                                                  │  │
 │  │  ┌──────────────────────┐             ┌───────────────────────┐  │  │
 │  │  │ remnawave-bot        │             │ remnawave-bot-db      │  │  │
 │  │  │ (Long-Polling Engine)│────────────►│ PostgreSQL 16         │  │  │
 │  │  │ [NO EXPOSED PORTS!]  │             │ (Internal Port 5432)  │  │  │
 │  │  └───────────▲──────────┘             └───────────────────────┘  │  │
 │  │              │                        ┌───────────────────────┐  │  │
 │  │              └───────────────────────►│ remnawave-bot-redis   │  │  │
 │  │                                       │ Redis 7 (Alpine)      │  │  │
 │  │                                       │ (Internal Port 6379)  │  │  │
 │  │                                       └───────────────────────┘  │  │
 │  └──────────────┼───────────────────────────────────────────────────┘  │
 └─────────────────┼──────────────────────────────────────────────────────┘
                   │ Outbound HTTPS Long-Polling (Portless)
                   ▼
         ┌───────────────────┐
         │ Telegram Bot API  │
         └───────────────────┘
```

### Key Co-existence Safeguards:
- **Zero Ingress Host Ports**: The bot connects to Telegram using outbound HTTPS long-polling. No host ports (including `80` and `443`) are required or bound, leaving your web reverse proxy untouched.
- **Completely Isolated Storage**: PostgreSQL 16 and Redis 7 services live in an isolated internal bridge network with **no host port mappings**. They will never collide with existing PostgreSQL or Redis instances used by Remnawave v3.
- **Local Loopback Resolution**: Connects to your local Remnawave v3 container via `http://host.docker.internal:3000` or via your external domain URL with full TLS validation.

---

## 📦 Prerequisites & Compatibility

> [!IMPORTANT]
> **Remnawave v3+ Exclusive**: Remnabot is engineered specifically for **Remnawave v3.0.0 or higher**. Remnawave v2 is **NOT** supported.

### System Requirements:
- **Operating System**: Linux (Ubuntu 22.04+ / Debian 12+), macOS, or Windows Server.
- **Runtime**: Docker Engine 24.0+ and Docker Compose v2 (Recommended), or Python 3.12+.
- **Hardware**: Minimum 1 vCPU, 512MB RAM available for bot containers.

---

## 🚀 Quick Start

### Method 1: Docker Compose (Recommended)

#### 1. Clone the repository
```bash
git clone https://github.com/nzrmohammad/Remnabot.git remnawave-bot
cd remnawave-bot
```

#### 2. Configure environment credentials
```bash
cp .env.example .env
nano .env
```
*(Configure your `BOT_TOKEN`, `ADMIN_IDS`, `ADMIN_CHAT_ID`, and Remnawave v3 connection settings).*

#### 3. Launch the complete stack
```bash
docker compose up -d --build
```

> [!NOTE]
> **Zero Manual Migrations Required**: The bot includes an autonomous native schema initialization engine. On first startup, all PostgreSQL tables, constraints, foreign keys, and indexes are provisioned automatically without needing Alembic or external CLI migration scripts.

#### 4. Verify deployment
```bash
# Check container status
docker compose ps

# Follow live output logs
docker compose logs -f bot
```

---

### Method 2: Bare-Metal Deployment

For environments running directly on the host system without Docker:

```bash
# 1. Install system dependencies
sudo apt update && sudo apt install -y python3-full python3-venv git postgresql redis-server

# 2. Provision local database
sudo -u postgres psql -c "CREATE DATABASE remnabot;"
sudo -u postgres psql -c "CREATE USER remnabot WITH ENCRYPTED PASSWORD 'YourSecurePassword';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE remnabot TO remnabot;"

# 3. Create virtual environment & install requirements
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Launch the application
python -m bot.main
```

---

## 🔄 Updating Guide

Upgrading to the latest release does not require reinstalling or changing your configuration:

### Method 1: Docker Compose (Recommended)
```bash
# 1. Navigate to the bot directory
cd remnawave-bot

# 2. Pull the latest release from GitHub
git pull origin main

# 3. Rebuild and restart the containers (zero database loss)
docker compose up -d --build

# 4. View live deployment logs
docker compose logs -f bot
```

### Method 2: Bare-Metal Deployment
```bash
cd remnawave-bot
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart remnabot
```

> [!TIP]
> **Zero Manual Migrations**: Thanks to Remnabot's autonomous **Self-Healing Schema Engine**, newly introduced database columns, indexes, and tables are provisioned on the fly upon container boot. No manual Alembic or SQL migration commands are required.

---

## 💾 Migration & Server Relocation

To migrate the bot and all operational data to a new server or restore from a backup:

### Step 1: Export Database Dump on Old Server
```bash
# Docker Compose:
docker compose exec -t db pg_dump -U remnabot remnabot > remnabot_backup.sql

# Bare-Metal:
pg_dump -U remnabot -d remnabot -F c -b -v -f remnabot_backup.dump
```

### Step 2: Transfer Backup & Credentials to New Server
```bash
scp remnabot_backup.sql .env root@NEW_SERVER_IP:/root/
```

### Step 3: Launch and Restore on New Server
```bash
# 1. SSH into the new server and clone the repository
ssh root@NEW_SERVER_IP
git clone https://github.com/nzrmohammad/Remnabot.git remnawave-bot
cd remnawave-bot

# 2. Place your existing .env configuration file in the project folder
mv /root/.env .env

# 3. Start database and cache containers
docker compose up -d

# 4. Restore the database dump into the PostgreSQL container
cat /root/remnabot_backup.sql | docker compose exec -T db psql -U remnabot remnabot

# 5. Restart the bot container to apply the restored data
docker compose restart bot
```

---

## ⚙️ Configuration Guide (`.env`)

All primary credentials are configuration-driven via `.env`. In-bot operational parameters (cards, quotas, support handles) are configurable interactively via Telegram.

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `BOT_TOKEN` | **Yes** | — | Telegram Bot API token obtained from [@BotFather](https://t.me/BotFather). |
| `ADMIN_IDS` | **Yes** | — | Numeric Telegram IDs of super-administrators (e.g. `[123456789]`). |
| `ADMIN_CHAT_ID` | **Yes** | — | Target Admin Supergroup or Channel ID for receipts, logs, and backups (e.g. `-1001234567890`). |
| `REMNAWAVE_BASE_URL` | **Yes** | — | Base URL of your Remnawave v3+ Panel (e.g. `https://panel.example.com` or `http://host.docker.internal:3000`). |
| `REMNAWAVE_TOKEN` | **Yes** | — | API Token generated in Remnawave Panel (`Admin ➔ API Tokens`). |
| `DATABASE_URL` | **Yes** | — | PostgreSQL async connection string (`postgresql+asyncpg://user:pass@host:5432/dbname`). |
| `ADMIN_TOPIC_TOPUPS` | No | *(empty)* | Optional topic ID for card-to-card deposit review queues. |
| `ADMIN_TOPIC_ORDERS` | No | *(empty)* | Optional topic ID for new service purchases and renewal logs. |
| `ADMIN_TOPIC_SUPPORT` | No | *(empty)* | Optional topic ID for user support inquiries and forward messages. |
| `ADMIN_TOPIC_ALERTS` | No | *(empty)* | Optional topic ID for system alerts, reconcile warnings, and database backups. |
| `ADMIN_TOPIC_CRYPTO` | No | *(empty)* | Optional topic ID for automated crypto pricing alerts and TON payment logs. |
| `CRYPTO_ENABLED` | No | `false` | Enable or disable direct crypto (TON) top-up option for users (`true` / `false`). |
| `TON_WALLET_ADDRESS` | No | *(empty)* | Public TON wallet address (UQ... or EQ...) for receiving on-chain payments. |
| `TON_RATE_TOMAN` | No | `0` | Manual fallback TON exchange rate in Toman (editable in-bot anytime). |
| `USDT_RATE_TOMAN` | No | `95000` | Benchmark Tether (USDT) price in Toman used for global Binance/TonAPI price calculation. |
| `IRAN_PROXY` | No | *(empty)* | Optional HTTP/SOCKS5 proxy for domestic Iranian exchanges when hosted on a foreign VPS. |
| `CARD_NUMBER` | No | *(empty)* | Bank card number for manual card-to-card deposits (empty disables card deposits). |
| `CARD_HOLDER` | No | *(empty)* | Cardholder full name displayed to users during card-to-card deposits. |
| `TOPUP_MIN_AMOUNT` | No | `10000` | Minimum wallet deposit threshold in Toman. |
| `TIMEZONE` | No | `Asia/Tehran` | Timezone identifier for Jalali conversions and scheduled fiscal reporting. |
| `REDIS_URL` | No | *(empty)* | Optional Redis connection string for distributed FSM storage. Defaults to memory storage when empty. |
| `SENTRY_DSN` | No | *(empty)* | Optional Sentry DSN endpoint for real-time error reporting and application telemetry. |

---

## ⏰ Background Schedulers & Lifecycle Engine

Remnabot executes asynchronous automation routines using an internal non-blocking scheduler:

| Task Name | Interval | Responsibility |
| :--- | :---: | :--- |
| `reconcile_loop` | **10 min** | Synchronizes panel subscribers with local database, links Telegram IDs, and reconciles state. |
| `devices_loop` | **5 min** | Inspects active HWID connections and terminates sessions exceeding plan device limits. |
| `expiry_loop` | **60 min** | Dispatches pre-expiry countdown warnings (3 days, 1 day, Day 0), enforces grace periods, and auto-disables expired panel subscriptions. |
| `alerts_loop` | **180 min** | Evaluates bandwidth consumption thresholds (80%, 90%, 100%) and delivers proactive renewal alerts. |
| `crypto_rates_loop` | **4x Daily (00:00, 06:00, 12:00, 18:00)** | Queries live TON market rates (Nobitex/Bitpin or Binance/TonAPI global fallback) and dispatches interactive price alerts to the crypto topic. |
| `retention_loop` | **12 hours** | Identifies users whose services expired 7 days ago and sends personalized win-back discount promotions. |
| `auto_backup_loop` | **Daily @ 03:00** | Generates an encrypted database snapshot and dispatches the document to the Telegram admin chat. |
| `nightly_report_loop`| **Daily @ 23:59** | Compiles panel status, node bandwidths by country flag, active users, and 3-day expirations. |
| `weekly_report_loop` | **Fri @ 23:59** | Calculates top 20 weekly consumers and daily champions from Saturday to Friday. |
| `monthly_report_loop`| **Last Day @ 23:59**| Produces comprehensive monthly fiscal and bandwidth rollups for the Jalali month. |
| `heartbeat_loop` | **60 sec** | Touches `/tmp/bot_heartbeat` to satisfy Docker container healthcheck probes. |

---

## 🛠 Store & Operations Management

Administrators can configure live store variables on the fly without editing `.env` or rebooting containers:

### Dynamic Settings Matrix (`Admin Panel ➔ ⚙️ Store Settings`)
- **Card-to-Card Configuration**: Update bank card numbers, cardholder names, and minimum deposit thresholds.
- **💎 Direct Crypto (TON) Gateway**:
  - Toggle crypto payment status (`⚡️ Gateway Status : ✅ / ❌`).
  - Configure public TON wallet address (`UQ...` / `EQ...`).
  - Configure manual fallback TON exchange rate (`Conversion Rate`).
  - Set benchmark Tether price (`💵 Baseline USDT Rate`) for resilient global calculation (`Binance TON/USD × USDT Rate`) with zero geo-blocking from foreign servers.
  - Optional Iranian forward proxy support (`IRAN_PROXY`) for domestic exchanges.
  - Real-time instant price query (`🔄 Live Rate Query`) directly inside Telegram.
  - 1-click update buttons dispatched 4x daily to the dedicated Crypto forum topic.
- **Free Trial Management**: Toggle 1-day free trial issuance (`✅` / `❌`), configure allowed quotas, and set trial duration.
- **Affiliate & Referral Settings**: Enable or disable referral programs, set traffic reward percentages, and adjust qualification criteria.
- **Supergroup Forum Topic Routing**: Route automated alerts and operational logs into dedicated Telegram forum topics:
  - 💳 **Top-ups Topic**: Deposit receipts and wallet verification queues.
  - 🛒 **Orders Topic**: New plan orders and subscription renewals.
  - 💎 **Crypto Topic**: Live TON market rate notifications and crypto payment logs.
  - 🆘 **Support Topic**: Customer tickets and inquiry messages.
  - 🚨 **Alerts Topic**: Node health alerts and automated daily database dumps.

---

## 🗺 Project Roadmap

- [ ] **📱 Telegram Mini App (TMA / WebApp)**: A sleek WebApp client featuring visual bandwidth gauges, interactive QR code displays, and in-app checkout.
- [ ] **⚡ Remnawave v3 Event Webhooks**: Immediate real-time callback processing for instant traffic exhaustion and plan event synchronization.
- [x] **💎 Direct On-Chain Crypto Gateway**: Native TON payments with Tonkeeper / Telegram Wallet 1-tap deep links, multi-source price fetching, and automated topic alerts.
- [ ] **🌐 Automated Multi-Chain Crypto Gateways**: Automated on-chain transaction monitoring for USDT (TRC-20) and TRX.
- [ ] **📲 Protocol Deep Links**: One-click configuration import for `v2rayNG`, `Sing-box`, `Streisand`, and `Happ`.
- [ ] **📈 Advanced Financial Analytics**: CSV and Excel export for ledger records, customer rosters, and tax reporting.

---

## 🧪 Testing & Quality Assurance

Remnabot maintains a strict test-driven development workflow with **84 passing unit & integration tests** covering database models, repositories, business logic services, and FSM handlers:

```bash
# Execute test suite
pytest -v

# Perform code quality and linting verification
ruff check bot/ tests/
```

---

## 👨‍💻 Community & License

- **Author**: Mohammad
- **Telegram Channel**: [@Nzrmohammad](https://t.me/Nzrmohammad)
- **License**: [MIT License](LICENSE)
