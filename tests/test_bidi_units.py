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
