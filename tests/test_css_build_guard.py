"""Guard test for CSS build pipeline, Tailwind tokens, and dynamic class prevention."""
import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
STATIC_CSS_DIR = ROOT_DIR / "bot" / "web" / "static" / "css"
STATIC_JS_DIR = ROOT_DIR / "bot" / "web" / "static" / "js"


def test_package_json_and_tailwind_scripts():
    """Verify package.json contains build:css and required Tailwind tools."""
    pkg_file = ROOT_DIR / "package.json"
    assert pkg_file.exists(), "package.json is missing!"

    data = json.loads(pkg_file.read_text(encoding="utf-8"))
    scripts = data.get("scripts", {})
    assert "build:css" in scripts, "build:css script is missing in package.json!"
    assert "watch:css" in scripts, "watch:css script is missing in package.json!"

    dev_deps = data.get("devDependencies", {})
    assert "tailwindcss" in dev_deps, "tailwindcss is missing from devDependencies!"


def test_tailwind_config_tokens():
    """Verify tailwind.config.js extends slate-750 and fadeIn animation."""
    cfg_file = ROOT_DIR / "tailwind.config.js"
    assert cfg_file.exists(), "tailwind.config.js is missing!"

    cfg_text = cfg_file.read_text(encoding="utf-8")
    assert "slate-750" in cfg_text, "slate-750 color token missing in tailwind.config.js!"
    assert "fadeIn" in cfg_text, "fadeIn keyframes/animation missing in tailwind.config.js!"


def test_no_dynamic_color_interpolation_in_js():
    """Ensure developers don't construct class names dynamically via template literals."""
    pattern = re.compile(r'(?:bg|text|border|ring|from|to|via)-\$\{[^}]+\}')
    violations = []

    for js_file in STATIC_JS_DIR.glob("*.js"):
        content = js_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if pattern.search(line):
                violations.append(f"{js_file.name}:{line_no} -> {stripped}")

    assert not violations, (
        f"Found dynamic Tailwind class construction in JS! Use a static lookup map instead:\n"
        + "\n".join(violations)
    )


def test_tailwind_compiled_output_contains_essential_tokens():
    """Ensure tailwind.min.css was built with critical utilities."""
    min_css = STATIC_CSS_DIR / "tailwind.min.css"
    assert min_css.exists(), "tailwind.min.css is missing!"

    css_text = min_css.read_text(encoding="utf-8")
    assert r"min-h-\[36px\]" in css_text, "min-h-[36px] not found in tailwind.min.css!"
    assert r"min-w-\[36px\]" in css_text, "min-w-[36px] not found in tailwind.min.css!"
    assert "slate-750" in css_text, "slate-750 utility not generated in tailwind.min.css!"
    assert "fadeIn" in css_text, "fadeIn animation not compiled in tailwind.min.css!"
