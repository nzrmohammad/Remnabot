"""BiDi isolation guard: human_bytes()/fmtTraffic must never leak an
unprotected 'NN GB' into RTL Persian context (Telegram & web)."""
import bot.services.formatting as fmt_mod


def test_human_bytes_is_bidi_isolated():
    out = fmt_mod.human_bytes(50 * 1024**3)
    assert out.startswith("\u2066")
    assert out.endswith("\u2069")
    assert "GB" in out


def test_human_bytes_plain_values_unchanged():
    p = fmt_mod._human_bytes_plain
    assert p(0) == "0 MB"
    assert p(1 * fmt_mod.GB) == "1.00 GB"
    assert p(1 * fmt_mod.TB) == "1.00 TB"
    assert p(500 * fmt_mod.MB) == "500.00 MB"


def test_isolation_chars_are_hidden_and_rare():
    out = fmt_mod.human_bytes(5 * 1024**3)
    assert len(out) == len("\u20665.00 GB\u2069")


def test_ltr_frag_wraps_arbitrary_fragments():
    assert fmt_mod.ltr_frag("25 GB") == "\u206625 GB\u2069"
    assert fmt_mod.ltr_frag("(GB)") == "\u2066(GB)\u2069"


def test_no_unisolated_unit_literals_in_bot_messages():
    """Guard: 'X GB' fragments interpolated next to Persian text must be isolated."""
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    risky = []
    unit_rx = re.compile(r"\{[^}]+\}\s*(GB|TB|MB)\b")
    iso = ("\u2066", "\u200e", "\u2068")
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, "bot")):
        dirnames[:] = [d for d in dirnames if d not in ("static", "templates", "__pycache__")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            src = open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace").read()
            for i, ln in enumerate(src.splitlines(), 1):
                s = ln.strip()
                if s.startswith(("#", "import", "from", "log")):
                    continue
                if unit_rx.search(ln) and re.search(r"[آ-ی]", ln) and not any(c in ln for c in iso) and "ltr_frag(" not in ln:
                    risky.append(f"{fn}:{i}: {s[:110]}")
    assert not risky, "Unisolated 'X GB' next to Persian text:\n" + "\n".join(risky)


def test_compact_traffic_and_account_bidi():
    from bot.handlers.account import _account_view_text, _format_account_btn
    from bot.handlers.inline import _format_traffic_compact

    assert fmt_mod.compact_traffic(0) == "\u20660 MB\u2069"
    assert fmt_mod.compact_traffic(500 * fmt_mod.MB) == "\u2066500 MB\u2069"
    assert fmt_mod.compact_traffic(20 * fmt_mod.GB) == "\u206620 GB\u2069"
    assert fmt_mod.compact_traffic(int(2.5 * fmt_mod.TB)) == "\u20662.5 TB\u2069"
    assert _format_traffic_compact(0, 10 * fmt_mod.GB) == "\u206610 GB\u2069"

    acc = {
        "id": 1,
        "username": "ali",
        "status": "ACTIVE",
        "trafficLimitBytes": 50 * fmt_mod.GB,
        "userTraffic": {"usedTrafficBytes": 10 * fmt_mod.GB},
        "expireAt": "2027-01-01T00:00:00Z",
    }
    btn = _format_account_btn(acc, "fa")
    view = _account_view_text(acc, "fa")
    assert "\u206640 GB\u2069" in btn
    assert "GB 40" not in view
    assert "GB 50" not in view
    assert "\u206640 GB\u2069" in view
    assert "\u206650 GB\u2069" in view


def test_fa_locale_and_service_display_bidi_isolation():
    from bot.db.models import Service
    from bot.locales.texts import t
    from bot.services.service_display import service_block

    svc = Service(
        id=1, name="Pro", price=100_000, traffic_gb=50, duration_days=30,
        traffic_strategy="NO_RESET", hwid_limit=1, is_active=True,
    )
    block = service_block(svc, "fa")
    assert "\u206650 GB\u2069" in block
    assert "\u206680%\u2069" in t("fa", "alert_traffic", username="u", percent="80", remaining=fmt_mod.human_bytes(fmt_mod.GB))
    assert "\u206615%\u2069" in t("fa", "weekly_sum_more", percent="15")
    assert "\u200e\u2066" not in t("fa", "weekly_total", total=fmt_mod.human_bytes(fmt_mod.GB))
    assert "\u200e\u2066" not in t("fa", "monthly_day", date="1405/09/01", total=fmt_mod.human_bytes(fmt_mod.GB))
