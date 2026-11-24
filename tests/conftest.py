"""Global pytest isolation fixtures.

Guarantees that NO test can read or mutate data-dev/, data/, or data-dev/backups/.
"""

from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolate_runtime_paths(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect DATA_DIR, DB_PATH, and BACKUPS_DIR to an isolated tmp_path per test."""
    test_data_dir = tmp_path / "data"
    test_backups_dir = test_data_dir / "backups"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    test_backups_dir.mkdir(parents=True, exist_ok=True)
    test_db_path = test_data_dir / "app.db"

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATA_DIR", str(test_data_dir))
    # Prevent non-live tests from burning the developer's real .env API keys
    if not request.node.get_closest_marker("live"):
        for _k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_BASE_URL"):
            monkeypatch.delenv(_k, raising=False)

    import backend.config as cfg
    import backend.database as db_mod
    import backend.migrations.runner as runner_mod

    if not request.node.get_closest_marker("live"):
        monkeypatch.setattr(cfg, "ENV_VARS", {}, raising=False)
    monkeypatch.setattr(cfg, "DATA_DIR", test_data_dir, raising=False)
    monkeypatch.setattr(cfg, "DB_PATH", test_db_path, raising=False)
    monkeypatch.setattr(cfg, "BACKUPS_DIR", test_backups_dir, raising=False)
    monkeypatch.setattr(db_mod, "DB_PATH", test_db_path, raising=False)
    monkeypatch.setattr(runner_mod, "DB_PATH", test_db_path, raising=False)
    monkeypatch.setattr(runner_mod, "BACKUPS_DIR", test_backups_dir, raising=False)

    yield {
        "data_dir": test_data_dir,
        "db_path": test_db_path,
        "backups_dir": test_backups_dir,
    }
