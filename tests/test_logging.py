import logging
import os


def test_log_rotation_uses_rotating_handler(tmp_path, monkeypatch):
    """setup_logging must use RotatingFileHandler, not plain FileHandler."""
    monkeypatch.chdir(tmp_path)
    os.makedirs('logs', exist_ok=True)
    config = {'logging': {'file': 'logs/processor.log', 'level': 'INFO'}}

    # Clear any existing handlers to avoid state bleed between tests
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    audit = logging.getLogger('audit')
    for h in audit.handlers[:]:
        audit.removeHandler(h)

    from main import setup_logging
    setup_logging(config)

    from logging.handlers import RotatingFileHandler
    handler_types = [type(h) for h in logging.getLogger().handlers]
    assert RotatingFileHandler in handler_types, (
        f"Expected RotatingFileHandler in handlers, got: {handler_types}"
    )
