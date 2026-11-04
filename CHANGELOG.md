# Changelog

All notable changes to the **Remnabot** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-11-04

### Added
- **Core Architecture & Engine**:
  - High-performance asynchronous foundation built on `aiogram 3.x`, `aiohttp`, `SQLAlchemy (asyncpg)`, and `FastCache` (multi-tier memory L1 + Redis L2).
  - Automatic non-destructive schema migration (`init_db` in `bot/db/base.py`) that detects and applies missing model columns to existing database tables on startup.
  - Single-instance startup lock mechanism preventing duplicate bot dispatcher instances and `TelegramConflictError`.
  - Process heartbeat loop and `/health` monitoring endpoint for Docker `HEALTHCHECK` and external uptime monitors.

- **Telegram Mini App (TMA)**:
  - Full RTL/Persian responsive dashboard with native Telegram Theme parameters and haptic feedback integration.
  - Interactive live traffic charts, burn-rate calculation, smart volume depletion predictions, and per-country traffic breakdown.
  - Dynamic graphical bank card component with customizable themes and official BluBank branding.
  - Multi-account subscription management: one-click configuration copying, QR code generation, and multi-protocol key listings.
  - Support chat system with real-time bidirectional communication between users and administrators.

- **Financial & Payment Gateways**:
  - Automated Card-to-Card system with unique suffix allocation and Iranian bank SMS parser for instant automated wallet credit.
  - Manual Card-to-Card top-up flow with receipt upload and admin verification workflow in both Telegram chat and Web panel.
  - On-chain TON blockchain payment processor with TonCenter API verification, replay protection, and Tonkeeper deep linking.
  - Webview-safe TronLink payment redirection endpoint (`/api/user/topup/trx/redirect`) for seamless wallet invocation.
  - Telegram Stars native payment integration.
  - Unified user cache invalidation (`FastCache.invalidate_user`) ensuring immediate balance updates upon payment approval.

- **Store & Services**:
  - Catalog of active packages, tiered pricing, and dynamic Custom Plan builder with custom traffic/duration sliders.
  - Multi-tier customer loyalty program and promotional coupon code validation.
  - Background auto-renewal service (`auto_renew_sweep_loop`) for seamless subscription renewal via wallet balance.
  - Gift card voucher system with balance and service vouchers, shareable links, and instant redemption.

- **Administrative Infrastructure**:
  - Dedicated web admin dashboard with sales summaries, revenue charts, user management, and audit logs.
  - Node health and resource monitor: alerts Telegram supergroup topics when CPU/RAM exceeds 90% or nodes go offline.
  - Synchronized analytical reporting across Telegram bot summaries and web charts.
  - Scheduled database backup service with automatic Telegram admin delivery.

- **Quality Assurance & Guard Architecture**:
  - Comprehensive test suite containing 337 automated unit and integration tests with a 100% pass rate.
  - CSS Guard (`test_css_guard.py` & `test_css_build_guard.py`) enforcing tokenized themes, specificity budget, and zero dynamic class construction.
  - JS Wiring Guard (`test_js_wiring_guard.py`) validating all modal targets, input bindings, and `APP_MODAL_IDS`.
  - BiDi Isolation Guard (`test_traffic_bidi_guard.py`) guaranteeing proper RTL/LTR ordering for traffic units and Persian numbers.

### Changed
- Aligned daily bandwidth reporting calculation between bot text summaries and web chart endpoints (indexed to day offset `0`).
- Unified `FastCache` instance sharing across Aiogram dispatcher workflow data and aiohttp web application.
- Hardened auto-renewal database queries against non-numeric account identifiers and edge-case query states.

### Fixed
- Fixed admin receipt approval/rejection modal callbacks failing due to lazy function resolution.
- Fixed TronLink deep links failing inside Telegram Mini App webviews.
- Prevented layout collisions between loyalty tier pills and coupon discount badges in shop package cards.
- Fixed unhandled 500 error responses on gift creation and claim endpoints when receiving invalid JSON payloads.
