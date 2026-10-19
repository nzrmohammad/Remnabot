"""CI Guard Test: Recursively imports all Python modules in bot/ to guarantee

zero NameError (missing Any, text, func, etc.), SyntaxError, or ImportError
at application startup (e.g. inside Docker containers).
"""
import importlib
import pkgutil
from pathlib import Path


def test_all_bot_modules_importable():
    """Recursively import all modules under bot package to detect missing imports."""
    bot_path = Path(__file__).parent.parent / "bot"
    assert bot_path.is_dir(), f"Bot directory not found at {bot_path}"

    imported = 0
    errors = []

    for py_file in bot_path.rglob("*.py"):
        if py_file.name.startswith("__") and py_file.name != "__init__.py":
            continue
        # Convert path to module name: e.g. bot.handlers.admin_ops
        rel_path = py_file.relative_to(bot_path.parent)
        parts = list(rel_path.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        mod_name = ".".join(parts)

        try:
            importlib.import_module(mod_name)
            imported += 1
        except Exception as exc:
            errors.append(f"{mod_name} ({py_file.name}): {type(exc).__name__}: {exc}")

    assert not errors, (
        f"Found {len(errors)} unimportable modules in bot/!\n"
        + "\n".join(errors)
    )
    assert imported >= 40, f"Expected at least 40 modules to be imported, found {imported}"
