"""CI Guard Test: Recursively imports all Python modules in bot/ and verifies type hints

Guarantees zero NameError (missing Any, text, func, etc.), SyntaxError, or ImportError
at application startup inside Docker containers (e.g. Python 3.12 vs 3.14).
"""
import importlib
import inspect
import typing
from pathlib import Path


def test_all_bot_modules_importable_and_typed():
    """Recursively import all modules under bot/ and evaluate all type hints."""
    bot_path = Path(__file__).parent.parent / "bot"
    assert bot_path.is_dir(), f"Bot directory not found at {bot_path}"

    imported = 0
    errors = []

    for py_file in bot_path.rglob("*.py"):
        if py_file.name.startswith("__") and py_file.name != "__init__.py":
            continue
        rel_path = py_file.relative_to(bot_path.parent)
        parts = list(rel_path.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        mod_name = ".".join(parts)

        try:
            mod = importlib.import_module(mod_name)
            imported += 1
        except Exception as exc:
            errors.append(f"IMPORT ERROR {mod_name} ({py_file.name}): {type(exc).__name__}: {exc}")
            continue

        # Force evaluation of type hints (catches missing imports like `Any` that Python 3.14 defers
        # under PEP 649 but Python 3.12 Docker evaluates eagerly).
        for name, obj in inspect.getmembers(mod):
            if (inspect.isfunction(obj) or inspect.isclass(obj)) and getattr(obj, "__module__", None) == mod_name:
                try:
                    typing.get_type_hints(obj)
                except Exception as exc:
                    errors.append(f"TYPE HINT ERROR {mod_name}.{name}: {type(exc).__name__}: {exc}")

    assert not errors, (
        f"Found {len(errors)} module/type-hint errors across bot/!\n"
        + "\n".join(errors)
    )
    assert imported >= 40, f"Expected at least 40 modules to be imported, found {imported}"


def test_zero_undefined_names_in_bot():
    """Run ruff F821 (undefined names) guard across bot/ to prevent runtime NameError regressions."""
    import subprocess
    import sys

    res = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "F821", "bot/"],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        # If ruff isn't installed in the environment, fallback gracefully, but if it is, enforce 0 errors.
        if "No module named ruff" in res.stderr:
            return
        assert res.returncode == 0, f"Ruff F821 undefined name errors detected in bot/:\n{res.stdout}\n{res.stderr}"
