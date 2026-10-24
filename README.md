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
- [🚀 Production Deployment & Installation Guide](#-production-deployment--installation-guide)
  - [Stage 1: Telegram Supergroup & Forum Topics Setup](#stage-1-telegram-supergroup--forum-topics-setup)
  - [Stage 2: Telegram Bot & Administrator Credentials](#stage-2-telegram-bot--administrator-credentials)
  - [Stage 3: Remnawave v3 Panel Connection](#stage-3-remnawave-v3-panel-connection)
  - [Stage 4: Clone Repository & Configure Environment (`.env`)](#stage-4-clone-repository--configure-environment-env)
  - [Stage 5: Telegram Mini App (TMA) & Nginx Reverse Proxy](#stage-5-telegram-mini-app-tma--nginx-reverse-proxy)
  - [Stage 6: Orchestration Launch & Verification](#stage-6-orchestration-launch--verification)
  - [Stage 7: Telegram Menu Button Registration](#stage-7-telegram-menu-button-registration)
- [🔄 Updating Guide](#-updating-guide)
- [💾 Migration & Server Relocation](#-migration--server-relocation)
- [⚙️ Configuration Guide (`.env`)](#-configuration-guide-env)
- [⏰ Background Schedulers & Lifecycle Engine](#-background-schedulers--lifecycle-engine)
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
├── tests/                          # Comprehensive test suite (210 passing tests)
├── docker-compose.yml              # Production multi-container orchestration (Bot, DB, Redis)
├── Dockerfile                      # Optimized Python 3.12-slim multi-stage image
├── requirements.txt                # Pinned production dependencies
└── .env.example                    # Environment variable template
```

### Unified System Architecture & Zero-Conflict Deployment Topology

When hosting the bot on the same virtual server as **Remnawave v3**, Remnabot eliminates port collisions, database contention, and resource starvation using an isolated virtual network topology:

```text
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                      HOST SERVER                                       │
 │                                                                                        │
 │   ┌───────────────────────────┐                     ┌──────────────────────────────┐   │
 │   │    Remnawave v3 Panel     │                     │      Web Reverse Proxy       │   │
 │   │   (Cluster REST API v3)   │                     │   (Nginx / Caddy / Traefik)  │   │
 │   │    Port 3000 (Internal)   │                     │     Ports 80 & 443 (Host)    │   │
 │   └─────────────▲─────────────┘                     └──────────────▲───────────────┘   │
 │                 │ REST API                                         │ Reverse Proxy     │
 │                 │ (Internal/Loopback)                              │ (app.yourdomain)  │
 │   ┌─────────────┴──────────────────────────────────────────────────┴───────────────┐   │
 │   │             Isolated Docker Virtual Network (`remnawave-network`)              │   │
 │   │                                                                                │   │
 │   │   ┌────────────────────────────────────────────────────────────────────────┐   │   │
 │   │   │                     remnawave-bot (Main Service)                       │   │   │
 │   │   │   • AsyncIO / aiogram 3.31+ Long-Polling Engine (Portless)             │   │   │
 │   │   │   • Embedded Aiohttp Web Server (Port 8080 - Mini App & REST APIs)     │   │   │
 │   │   │   • Autonomous Background Schedulers & Telemetry Workers               │   │   │
 │   │   └──────────────────────┬──────────────────────────┬──────────────────────┘   │   │
 │   │                          │                          │                          │   │
 │   │                          ▼                          ▼                          │   │
 │   │              ┌───────────────────────┐  ┌───────────────────────┐              │   │
 │   │              │   remnawave-bot-db    │  │  remnawave-bot-redis  │              │   │
 │   │              │    (PostgreSQL 16)    │  │   (Redis 7 Alpine)    │              │   │
 │   │              │ Internal Port 5432    │  │ Internal Port 6379    │              │   │
 │   │              └───────────────────────┘  └───────────────────────┘              │   │
 │   └──────────────────────────┬─────────────────────────────────────────────────────┘   │
 └──────────────────────────────┼─────────────────────────────────────────────────────────┘
                                │ Outbound HTTPS Long-Polling (No open ingress bot ports)
                                ▼
                    ┌───────────────────────┐
                    │   Telegram Bot API    │
                    └───────────────────────┘
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

## 🚀 Production Deployment & Installation Guide

A complete, battle-tested installation workflow for deploying Remnabot alongside Remnawave v3 on a fresh Linux server.

```text
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   DEPLOYMENT PIPELINE                                  │
 │                                                                                        │
 │  [Stage 1] Telegram Supergroup ──► [Stage 2] Bot & Admin IDs ──► [Stage 3] Remnawave  │
 │  (Forum Topics & Permissions)      (@BotFather & @userinfobot)   (v3 Panel REST API)  │
 │                                                                                        │
 │  [Stage 4] Clone & Configure   ──► [Stage 5] Reverse Proxy   ──► [Stage 6] Launch Bot │
 │  (.env credentials)                (Nginx SSL & 502 Fix)         (Docker Compose Up)  │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### Stage 1: Telegram Supergroup & Forum Topics Setup

To keep financial transactions, error traces, automated backups, and user support cleanly separated, Remnabot organizes operations into a **Telegram Supergroup with Forum Topics enabled**.

#### 1. Create Supergroup & Enable Topics:
1. In Telegram, create a new Group (Recommended name: **`🏢 Remnabot Operations Hub`**).
2. Open **Group Settings (Edit Group) ➔ Permissions ➔ Topics** and turn **ON** (enables Forum mode).
3. Add your bot into the Supergroup and promote it to **Administrator** with these rights:
   - ✅ Manage Topics
   - ✅ Delete Messages
   - ✅ Pin Messages
   - ✅ Send Messages

#### 2. Recommended Topics Architecture:
Create the following 9 topics inside your supergroup. Use the recommended names and icons for instant operational clarity:

| # | Topic Name | Icon | Environment Variable | In-Bot Setting | Automated Responsibility |
| :-: | :--- | :-: | :--- | :--- | :--- |
| **1** | **💳 Top-ups & Banking Receipts** (`Top-ups`) | 💳 | `ADMIN_TOPIC_TOPUPS` | `adm:set:topic_topups` | Card deposit slips, SHA-256 duplicate guards, 1-tap Approve/Reject buttons, and TON on-chain logs. |
| **2** | **🛒 Orders & Renewals** (`Orders`) | 🛒 | `ADMIN_TOPIC_ORDERS` | `adm:set:topic_orders` | Real-time purchase alerts, renewals, plan upgrades, and free trial issuances. |
| **3** | **🎧 Support & User Inquiries** (`Support`) | 🎧 | `ADMIN_TOPIC_SUPPORT` | `adm:set:topic_support` | Live 2-way support desk. Admins reply directly inside this topic to forward answers to users. |
| **4** | **🖥️ Server Nodes & Health** (`Nodes`) | 🖥️ | `ADMIN_TOPIC_NODES` | `adm:set:topic_nodes` | Remnawave node status, offline/online triggers, CPU/RAM telemetry, and core versions. |
| **5** | **📊 Fiscal & Bandwidth Reports** (`Reports`) | 📊 | `ADMIN_TOPIC_REPORTS` | `adm:set:topic_reports` | Daily (23:59), weekly, and monthly fiscal summaries, node traffic breakdown by country flags, and top users. |
| **6** | **🚨 System & Expiry Alerts** (`Alerts`) | 🚨 | `ADMIN_TOPIC_ALERTS` | `adm:set:topic_alerts` | Bandwidth consumption warnings (80%, 90%, 100%), pre-expiry countdowns, and grace-period enforcements. |
| **7** | **💾 Automated Database Backups** (`Backups`) | 💾 | `ADMIN_TOPIC_BACKUPS` | `adm:set:topic_backups` | Encrypted daily PostgreSQL snapshot dispatch (03:00 AM) with auto-pruning of older dumps. |
| **8** | **💎 Crypto & Live Market Rates** (`Crypto`) | 💎 | `ADMIN_TOPIC_CRYPTO` | `adm:set:topic_crypto` | 4x daily market rate updates (TON/USDT) with interactive 1-click price sync buttons. |
| **9** | **⚠️ System Error Logs** (`Error Logs`) | ⚠️ | `ADMIN_TOPIC_ERRORS` | `adm:set:topic_errors` | Real-time traceback dumps and runtime alerts for rapid diagnostics. |

#### 3. Extracting `ADMIN_CHAT_ID` and Topic IDs:
- **`ADMIN_CHAT_ID`**: Add `@RawDataBot` or `@userinfobot` to the group, or copy the link of any message in the group (`https://t.me/c/2456789012/123`). Prefix the ID with `-100` (e.g., `-1002456789012`).
- **Topic IDs (`ADMIN_TOPIC_*`)**:
  - In Telegram Desktop or Mobile, right-click (or tap & hold) on the topic and choose **"Copy Link to Topic"**.
  - Example link: `https://t.me/c/2456789012/35` ➔ Topic ID is `35`.
  - *Tip: You can either define these in `.env`, or configure them on the fly inside Telegram via `👑 Admin Panel ➔ ⚙️ Store Settings ➔ 📁 Topic Settings`.*

---

### Stage 2: Telegram Bot & Administrator Credentials

1. Open Telegram and message [@BotFather](https://t.me/BotFather):
   - Send `/newbot`, choose a title and username ending in `bot`.
   - Copy your **API Token** (e.g. `789123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`).
2. Get your numeric Admin Telegram ID:
   - Message [@userinfobot](https://t.me/userinfobot) to get your numeric ID (e.g. `123456789`).
   - If you have multiple admins, separate IDs with commas: `123456789, 987654321`.

---

### Stage 3: Remnawave v3 Panel Connection

1. Log in to your Remnawave v3 Panel as an Administrator.
2. Go to **Admin ➔ API Tokens** and generate a new token with full management rights.
3. Determine your connection URL:
   - **Same Server (Recommended)**: `http://host.docker.internal:3000` (zero latency and zero round-trips over the internet).
   - **Remote Server**: Your public HTTPS panel domain (e.g. `https://panel.yourdomain.com`).

---

### Stage 4: Clone Repository & Configure Environment (`.env`)

```bash
# 1. Clone the repository
git clone https://github.com/nzrmohammad/Remnabot.git remnawave-bot
cd remnawave-bot

# 2. Create your environment configuration file
cp .env.example .env
nano .env
```

Set your core production variables:
```env
# --- 1. Telegram Credentials ---
BOT_TOKEN=123456789:ABCDefghIJKlmnoPQRstuvWXyz
ADMIN_IDS=123456789
ADMIN_CHAT_ID=-1001234567890

# --- 2. Remnawave v3 Connection ---
REMNAWAVE_BASE_URL=http://host.docker.internal:3000
REMNAWAVE_TOKEN=your_remnawave_api_token_here

# --- 3. Database Credentials ---
DATABASE_URL=postgresql+asyncpg://remnabot:remnabot@db:5432/remnabot

# --- 4. Mini App & Web Configuration ---
WEB_ENABLED=true
WEB_PORT=8080
WEB_APP_URL=https://app.yourdomain.com

# Required if Nginx connects via host.docker.internal:8080
WEB_BIND_IP=0.0.0.0
```

---

### Stage 5: Telegram Mini App (TMA) & Nginx Reverse Proxy

Remnabot features a built-in, asynchronous, high-performance web service delivering **two dedicated Telegram Mini Apps**:
1. **👤 Client Portal WebApp (`/app`)**: Visual bandwidth circular gauge, collapsible per-country daily traffic accordion, interactive Lucky Wheel (6-tier prizes with automatic Remnawave quota allocation), story card generator, 1-tap app importers (`Incy`, `Happ`, `v2rayNG`, `Hiddify`, `Streisand`), live node ping latency tester, and IP/DNS leak detector.
2. **👑 Cluster Admin Suite (`/admin`)**: Real-time KPIs (total users, active subscriptions, today's revenue, cluster-wide bandwidth, online sessions), cluster node telemetry (CPU/RAM/Xray restart), instant user modifier (`+GB`, `+Days`, Kill HWID sessions, Ban toggle), support ticket desk, and instant broadcast messaging.

#### 1. WebSocket Upgrade Mapping (`nginx.conf`):
Ensure your Nginx configuration contains the `$connection_upgrade` map inside the top-level `http {}` block:

```nginx
http {
    # WebSocket connection upgrade mapping
    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }
    ...
}
```

#### 2. Nginx Upstream & Server Block:
Add the upstream and server block to your Nginx configuration (e.g. `/etc/nginx/conf.d/remnabot.conf` or inside your Remnawave Nginx volume):

```nginx
# --- Remnabot Web Upstream ---
upstream remnabot {
    # 1. Recommended (Zero-Exposure): Direct internal Docker network connection
    server remnawave-bot:8080;
    
    # 2. Alternative (via host gateway; requires WEB_BIND_IP=0.0.0.0 in .env):
    # server host.docker.internal:8080;
    
    # 3. If Nginx is installed directly on Host OS (outside Docker):
    # server 127.0.0.1:8080;

    keepalive 32;
}

# --- Telegram Mini App (Remnabot Telegram Mini App) ---
server {
    server_name app.yourdomain.com;
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;

    ssl_certificate "/etc/nginx/ssl/app.yourdomain.com_fullchain.pem";
    ssl_certificate_key "/etc/nginx/ssl/app.yourdomain.com_privkey.key";
    ssl_trusted_certificate "/etc/nginx/ssl/app.yourdomain.com_fullchain.pem";

    # Essential: Grants permission for Telegram WebApp iframe rendering
    add_header Content-Security-Policy "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org telegram:;" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    location / {
        proxy_pass http://remnabot;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 15s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        tcp_nodelay on;
    }
}
```

> [!TIP]
> **Zero-Exposure Direct Container Networking (Recommended):**
> Remnabot's `docker-compose.yml` automatically connects the bot to `remnawave-network`.
> In your Nginx upstream, setting `server remnawave-bot:8080;` routes traffic entirely over Docker's internal virtual bridge with zero port exposure on the public host, completely preventing 502 Bad Gateway!
> 
> *If you instead use `host.docker.internal:8080`, ensure `WEB_BIND_IP=0.0.0.0` is set in `remnawave-bot/.env`.*

#### 3. SSL Certificate Setup for Co-Located Remnawave Deployments (Docker Volume Mounting):

When the Mini App reverse proxy or Nginx runs on the **same server as the Remnawave panel** inside a Docker container, the SSL certificate files for your bot's dedicated subdomain (e.g. `app.yourdomain.com`) must be mounted as read-only (`:ro`) in the `volumes` section of the Nginx container:

```yaml
services:
  # Primary panel Nginx service or shared reverse proxy
  remnawave-nginx:
    volumes:
      - /etc/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - /etc/nginx/conf.d:/etc/nginx/conf.d:ro
      # Mount the bot Mini App SSL certificate files into the container:
      - ./app.yourdomain.com_fullchain.pem:/etc/nginx/ssl/app.yourdomain.com_fullchain.pem:ro
      - ./app.yourdomain.com_privkey.key:/etc/nginx/ssl/app.yourdomain.com_privkey.key:ro
```

Then in your Nginx site configuration file (`/etc/nginx/conf.d/remnabot.conf`), reference the paths inside the container:

```nginx
server {
    server_name app.yourdomain.com;
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;

    ssl_certificate "/etc/nginx/ssl/app.yourdomain.com_fullchain.pem";
    ssl_certificate_key "/etc/nginx/ssl/app.yourdomain.com_privkey.key";
    ssl_trusted_certificate "/etc/nginx/ssl/app.yourdomain.com_fullchain.pem";
    ...
}
```

---

### Stage 6: Orchestration Launch & Verification

Launch the stack using Docker Compose:

```bash
# 1. Ensure external Remnawave docker network exists (if connecting to an existing cluster)
docker network create remnawave-network 2>/dev/null || true

# 2. Build and start containers in the background
docker compose up -d --build

# 2. Check container health status
docker compose ps
# Both 'remnawave-bot', 'remnawave-bot-db', and 'remnawave-bot-redis' should show 'Up' / 'healthy'.

# 3. Follow live startup logs
docker compose logs -f bot
```

> [!NOTE]
> **Autonomous Self-Healing Schema**: On first boot, the bot automatically provisions all PostgreSQL tables, foreign keys, and indexes. Zero manual migration commands or SQL scripts are necessary.

#### Verify Healthcheck Endpoint:
Run on your server:
```bash
curl -I https://app.yourdomain.com/health
```
You should receive `HTTP/1.1 200 OK` with JSON payload:
```json
{"status": "ok", "service": "remnabot-tma"}
```

---

### Stage 7: Telegram Menu Button Registration

Once deployed, make the Mini App directly accessible to every user with one tap:

1. **Inline Dashboard Buttons**: Send `/start` to your bot in Telegram. The **`📱 Client Portal (Mini App)`** button appears automatically for users, and **`👑 Cluster Web Panel`** appears for admins.
2. **Permanent Bot Menu Button**:
   - Message [@BotFather](https://t.me/BotFather).
   - Send `/setmenubutton` and select your bot.
   - Enter your Mini App URL: `https://app.yourdomain.com/app`
   - Set the button title (e.g. `Dashboard 📱` or `App 🚀`).
   - The Mini App is now pinned permanently beside the user's chat input field.

---

## 🔄 Updating Guide

Upgrading to the latest release does not require reinstalling or changing your configuration:

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

> [!TIP]
> **Zero Manual Migrations**: Thanks to Remnabot's autonomous **Self-Healing Schema Engine**, newly introduced database columns, indexes, and tables are provisioned on the fly upon container boot. No manual Alembic or SQL migration commands are required.

---

## 💾 Migration & Server Relocation

To migrate Remnabot and all user balances, orders, and configurations to a new server, choose either the **Native JSON Backup (Recommended)** or the **PostgreSQL SQL Dump**.

### Method 1: Native JSON Database Backup (Recommended)

Remnabot includes an integrated JSON backup engine (`bot/services/backup.py`) that exports all operational data (users, wallets, services, coupons, orders, settings, and logs) into a schema-agnostic, portable JSON format with atomic integrity.

#### Step 1: Generate JSON Backup on Current Server
You can generate a backup in two ways:
- **Via Telegram Bot**: Go to Admin Dashboard ➔ System Settings ➔ Tap **"💾 Backup Database"**. The bot will immediately send the `.json` file to your Telegram chat.
- **Via Server CLI**:
  ```bash
  docker compose exec bot python -c "import asyncio; from bot.db.base import async_session_factory; from bot.services.backup import create_database_backup; asyncio.run(create_database_backup(async_session_factory()))"
  ```
  The generated file is saved under `./backups/remnabot_backup_YYYYMMDD_HHMMSS.json`.

#### Step 2: Transfer Backup & Environment to New Server
```bash
scp backups/remnabot_backup_*.json .env root@NEW_SERVER_IP:/root/
```

#### Step 3: Setup & Restore on New Server
```bash
# 1. SSH into the new server and clone the repository
ssh root@NEW_SERVER_IP
git clone https://github.com/nzrmohammad/Remnabot.git remnawave-bot
cd remnawave-bot

# 2. Move your .env and backup file into place
mv /root/.env .env
mkdir -p backups
mv /root/remnabot_backup_*.json backups/

# 3. Start the containers (PostgreSQL schema is automatically provisioned on boot)
docker compose up -d

# 4. Restore the JSON backup into the database
BACKUP_FILE=$(ls backups/remnabot_backup_*.json | tail -n 1)
docker compose exec bot python -c "import asyncio; from bot.db.base import async_session_factory; from bot.services.backup import restore_database_backup; asyncio.run(restore_database_backup(async_session_factory(), '${BACKUP_FILE}'))"

# 5. Restart the bot container to refresh caches
docker compose restart bot
```

---

### Method 2: Standard PostgreSQL SQL Dump

Alternatively, you can perform a raw PostgreSQL dump:

```bash
# On Old Server:
docker compose exec -t db pg_dump -U remnabot remnabot > remnabot_backup.sql
scp remnabot_backup.sql .env root@NEW_SERVER_IP:/root/

# On New Server:
cd remnawave-bot
mv /root/.env .env
docker compose up -d
cat /root/remnabot_backup.sql | docker compose exec -T db psql -U remnabot remnabot
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
| `ADMIN_TOPIC_ALERTS` | No | *(empty)* | Optional topic ID for system alerts and reconcile warnings. |
| `ADMIN_TOPIC_BACKUPS` | No | *(empty)* | Optional dedicated topic ID for automated database backup files. |
| `ADMIN_TOPIC_REPORTS` | No | *(empty)* | Optional topic ID for daily/weekly executive fiscal and bandwidth reports. |
| `ADMIN_TOPIC_NODES` | No | *(empty)* | Optional topic ID for server node status, health, and offline alerts. |
| `ADMIN_TOPIC_CRYPTO` | No | *(empty)* | Optional topic ID for automated crypto pricing alerts and TON payment logs. |
| `ADMIN_TOPIC_ERRORS` | No | *(empty)* | Optional topic ID for system traceback logs and error reports. |
| `CRYPTO_ENABLED` | No | `false` | Enable or disable direct crypto (TON) top-up option for users (`true` / `false`). |
| `TON_WALLET_ADDRESS` | No | *(empty)* | Public TON wallet address (UQ... or EQ...) for receiving on-chain payments. |
| `TON_RATE_TOMAN` | No | `0` | Manual fallback TON exchange rate in Toman (editable in-bot anytime). |
| `USDT_RATE_TOMAN` | No | `0` | Benchmark Tether (USDT) price in Toman used for global Binance/TonAPI price calculation. |
| `IRAN_PROXY` | No | *(empty)* | Optional HTTP/SOCKS5 proxy for domestic Iranian exchanges when hosted on a foreign VPS. |
| `CARD_NUMBER` | No | *(empty)* | Bank card number for manual card-to-card deposits (empty disables card deposits). |
| `CARD_HOLDER` | No | *(empty)* | Cardholder full name displayed to users during card-to-card deposits. |
| `TOPUP_MIN_AMOUNT` | No | `10000` | Minimum wallet deposit threshold in Toman. |
| `TIMEZONE` | No | `Asia/Tehran` | Timezone identifier for Jalali conversions and scheduled fiscal reporting. |
| `REDIS_URL` | No | *(empty)* | Optional Redis connection string for distributed FSM storage. Defaults to memory storage when empty. |

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

## 🧪 Testing & Quality Assurance

Remnabot maintains a strict test-driven development workflow with **210 passing unit & integration tests** covering database models, repositories, business logic services, and FSM handlers:

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
