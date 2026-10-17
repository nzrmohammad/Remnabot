"""CI Guard Test: Prevents regressions of raw un-isolated traffic concatenation."""
import re
from pathlib import Path

# Match raw template interpolations like `${foo} GB`, `${foo ?? 0} GB`, etc.
RAW_TRAFFIC_CONCAT = re.compile(r"\$\{[^}]+\}\s*(?:GB|MB|TB)\b")

FRONTEND_JS_DIR = Path("bot/web/static/js")
CHECKED_FILES = [
    "app.js",
    "admin.js",
    "charts.js",
    "shop.js",
    "story.js",
    "wheel.js",
    "wallet.js",
]


def test_no_raw_traffic_concatenation_in_js():
    """Ensure no developer adds raw `${var} GB` without using fmtTraffic."""
    violations = []
    for filename in CHECKED_FILES:
        filepath = FRONTEND_JS_DIR / filename
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if RAW_TRAFFIC_CONCAT.search(line):
                violations.append(f"{filename}:{line_num} -> {stripped}")

    assert not violations, (
        f"Found raw traffic string concatenation! Use fmtTraffic(...) instead:\n"
        + "\n".join(violations)
    )
