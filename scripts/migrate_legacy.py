"""Standalone legacy database migration runner for upgrading older schema versions.

Safe to run on existing deployments with pre-beta database schemas.
For fresh installs, Base.metadata.create_all handles table creation natively.

Usage:
    python -m scripts.migrate_legacy
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bot.db.base import Base, create_engine_and_sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def _table_columns(conn, table: str) -> set[str]:
    result = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :t"
        ),
        {"t": table},
    )
    return {row[0] for row in result}


async def migrate_legacy_schema(engine: AsyncEngine) -> None:
    """Idempotent fixes for tables created by older versions.

    `create_all` never alters existing tables, so known renames / new
    columns are patched here manually. Safe to run when upgrading an older DB.
    """
    async with engine.begin() as conn:
        # --- alert_state.account_uuid -> account_id (schema rename) ---- #
        cols = await _table_columns(conn, "alert_state")
        if cols and "account_id" not in cols and "account_uuid" in cols:
            await conn.execute(
                text("ALTER TABLE alert_state RENAME COLUMN account_uuid TO account_id")
            )
            logger.info("migrated alert_state.account_uuid -> account_id")

        # --- users.last_active_at, phone_number, birth_date (new columns) #
        cols = await _table_columns(conn, "users")
        if cols:
            if "last_active_at" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN last_active_at TIMESTAMPTZ")
                )
                logger.info("added users.last_active_at")
            if "phone_number" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(32)")
                )
                logger.info("added users.phone_number")
            if "birth_date" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN birth_date VARCHAR(32)")
                )
                logger.info("added users.birth_date")
            if "campaign_code" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN campaign_code VARCHAR(32)")
                )
                logger.info("added users.campaign_code")
            if "auto_renew" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN auto_renew BOOLEAN DEFAULT FALSE")
                )
                logger.info("added users.auto_renew")
            if "wheel_streak" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN wheel_streak INTEGER DEFAULT 0")
                )
                logger.info("added users.wheel_streak")
            if "wheel_last_spin_at" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN wheel_last_spin_at TIMESTAMPTZ")
                )
                logger.info("added users.wheel_last_spin_at")
            if "spin_tickets" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN spin_tickets INTEGER DEFAULT 0")
                )
                logger.info("added users.spin_tickets")

        # --- services: strategy / hwid / squad (new columns) ----------- #
        cols = await _table_columns(conn, "services")
        if cols:
            if "traffic_strategy" not in cols:
                await conn.execute(text(
                    "ALTER TABLE services ADD COLUMN traffic_strategy "
                    "VARCHAR(16) NOT NULL DEFAULT 'NO_RESET'"
                ))
                logger.info("added services.traffic_strategy")
            if "hwid_limit" not in cols:
                await conn.execute(
                    text("ALTER TABLE services ADD COLUMN hwid_limit INTEGER")
                )
                logger.info("added services.hwid_limit")
            if "squad_uuid" not in cols:
                await conn.execute(
                    text("ALTER TABLE services ADD COLUMN squad_uuid VARCHAR(64)")
                )
                logger.info("added services.squad_uuid")
            if "badge" not in cols:
                await conn.execute(
                    text("ALTER TABLE services ADD COLUMN badge VARCHAR(32)")
                )
                logger.info("added services.badge")

        # --- orders: status / refunded_at (new columns) ---------------- #
        cols = await _table_columns(conn, "orders")
        if cols:
            if "status" not in cols:
                await conn.execute(text(
                    "ALTER TABLE orders ADD COLUMN status "
                    "VARCHAR(10) NOT NULL DEFAULT 'paid'"
                ))
                logger.info("added orders.status")
            if "refunded_at" not in cols:
                await conn.execute(
                    text("ALTER TABLE orders ADD COLUMN refunded_at TIMESTAMPTZ")
                )
                logger.info("added orders.refunded_at")

        # --- report_settings columns (monthly, clean_reports, last_report_message_id, wheel_notify, wheel_notified, wheel_last_spin_at) --- #
        cols = await _table_columns(conn, "report_settings")
        if cols:
            if "monthly" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN monthly "
                        "BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )
                logger.info("added report_settings.monthly")
            if "clean_reports" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN clean_reports "
                        "BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )
                logger.info("added report_settings.clean_reports")
            if "last_report_message_id" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN last_report_message_id "
                        "BIGINT"
                    )
                )
                logger.info("added report_settings.last_report_message_id")
            if "wheel_notify" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN wheel_notify "
                        "BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )
                logger.info("added report_settings.wheel_notify")
            if "wheel_notified" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN wheel_notified "
                        "BOOLEAN NOT NULL DEFAULT FALSE"
                    )
                )
                logger.info("added report_settings.wheel_notified")
            if "wheel_last_spin_at" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN wheel_last_spin_at "
                        "TIMESTAMPTZ"
                    )
                )
                logger.info("added report_settings.wheel_last_spin_at")
            if "last_nightly_message_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE report_settings ADD COLUMN last_nightly_message_id BIGINT")
                )
                logger.info("added report_settings.last_nightly_message_id")
            if "last_weekly_message_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE report_settings ADD COLUMN last_weekly_message_id BIGINT")
                )
                logger.info("added report_settings.last_weekly_message_id")
            if "last_monthly_message_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE report_settings ADD COLUMN last_monthly_message_id BIGINT")
                )
                logger.info("added report_settings.last_monthly_message_id")
            if "last_wheel_message_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE report_settings ADD COLUMN last_wheel_message_id BIGINT")
                )
                logger.info("added report_settings.last_wheel_message_id")

        # --- topups.receipt_hash (duplicate-receipt fingerprint) --------- #
        cols = await _table_columns(conn, "topups")
        if cols and "receipt_hash" not in cols:
            await conn.execute(
                text("ALTER TABLE topups ADD COLUMN receipt_hash VARCHAR(128)")
            )
            logger.info("added topups.receipt_hash")
        if cols and "receipt_photo_id" not in cols:
            await conn.execute(
                text("ALTER TABLE topups ADD COLUMN receipt_photo_id VARCHAR(256)")
            )
            logger.info("added topups.receipt_photo_id")
        if cols and "admin_message_id" not in cols:
            await conn.execute(
                text("ALTER TABLE topups ADD COLUMN admin_message_id BIGINT")
            )
            logger.info("added topups.admin_message_id")

        if cols:
            try:
                async with conn.begin_nested():
                    # Deduplicate existing non-null receipt_hashes before index creation
                    await conn.execute(
                        text(
                            "UPDATE topups "
                            "SET receipt_hash = receipt_hash || '_dup_' || CAST(id AS VARCHAR) "
                            "WHERE id NOT IN ("
                            "    SELECT min_id FROM ("
                            "        SELECT MIN(id) AS min_id FROM topups WHERE receipt_hash IS NOT NULL GROUP BY receipt_hash"
                            "    ) t"
                            ") AND receipt_hash IS NOT NULL"
                        )
                    )
                    await conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS uq_topups_receipt_hash "
                            "ON topups (receipt_hash) WHERE receipt_hash IS NOT NULL"
                        )
                    )
            except Exception as exc:
                logger.debug("Unique index on topups.receipt_hash check: %s", exc)

        # --- users: is_banned, has_claimed_trial, referred_by_id (new columns) --- #
        cols = await _table_columns(conn, "users")
        if cols:
            if "is_banned" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE")
                )
                logger.info("added users.is_banned")
            if "has_claimed_trial" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN has_claimed_trial BOOLEAN NOT NULL DEFAULT FALSE")
                )
                logger.info("added users.has_claimed_trial")
            if "referred_by_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN referred_by_id BIGINT")
                )
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_users_referred_by_id ON users (referred_by_id)")
                )
                logger.info("added users.referred_by_id")
            if "full_name" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN full_name VARCHAR(128)")
                )
                logger.info("added users.full_name")
            if "phone_number" in cols:
                try:
                    async with conn.begin_nested():
                        await conn.execute(
                            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_number ON users (phone_number) WHERE phone_number IS NOT NULL")
                        )
                except Exception as exc:
                    logger.debug("Unique index on users.phone_number check: %s", exc)

        # --- orders: is_renewal and snapshot_data columns ----------------------- #
        cols = await _table_columns(conn, "orders")
        if cols and "is_renewal" not in cols:
            await conn.execute(
                text("ALTER TABLE orders ADD COLUMN is_renewal BOOLEAN DEFAULT FALSE")
            )
            logger.info("added orders.is_renewal")
        if cols and "snapshot_data" not in cols:
            await conn.execute(
                text("ALTER TABLE orders ADD COLUMN snapshot_data TEXT")
            )
            logger.info("added orders.snapshot_data")

        # --- crypto_invoices: tx_hash index ------------------------------------ #
        cols = await _table_columns(conn, "crypto_invoices")
        if cols and "tx_hash" in cols:
            try:
                async with conn.begin_nested():
                    await conn.execute(
                        text("CREATE UNIQUE INDEX IF NOT EXISTS uq_crypto_invoices_tx_hash ON crypto_invoices (tx_hash) WHERE tx_hash IS NOT NULL")
                    )
                logger.info("ensured uq_crypto_invoices_tx_hash unique index")
            except Exception as exc:
                logger.debug("Unique index on crypto_invoices.tx_hash check: %s", exc)

        # --- node_costs: currency column --------------------------------------- #
        cols = await _table_columns(conn, "node_costs")
        if cols and "currency" not in cols:
            await conn.execute(
                text("ALTER TABLE node_costs ADD COLUMN currency VARCHAR(8) DEFAULT 'EUR'")
            )
            logger.info("added node_costs.currency")

        # --- admin_logs: target_user_id column --------------------------------- #
        cols = await _table_columns(conn, "admin_logs")
        if cols and "target_user_id" not in cols:
            await conn.execute(
                text("ALTER TABLE admin_logs ADD COLUMN target_user_id BIGINT")
            )
            logger.info("added admin_logs.target_user_id")

        # --- Scale composite indexes ------------------------------------------- #
        scale_indexes = [
            ("ix_orders_status_created_at", "orders", "(status, created_at)"),
            ("ix_topups_status", "topups", "(status)"),
            ("ix_crypto_invoices_status", "crypto_invoices", "(status)"),
            ("ix_users_auto_renew", "users", "(auto_renew)"),
            ("ix_admin_logs_target_user_id", "admin_logs", "(target_user_id)"),
            ("ix_admin_logs_action_created", "admin_logs", "(action, created_at)"),
        ]
        for idx_name, tbl, cols_spec in scale_indexes:
            try:
                await conn.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} {cols_spec}")
                )
            except Exception as e:
                logger.debug("Scale index %s note: %s", idx_name, e)


async def main() -> None:
    logger.info("Starting legacy schema migration...")
    engine, _ = create_engine_and_sessionmaker()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await migrate_legacy_schema(engine)
    logger.info("Legacy schema migration completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
