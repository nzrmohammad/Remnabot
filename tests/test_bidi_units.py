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
    import re
    import os
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
