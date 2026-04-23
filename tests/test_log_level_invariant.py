"""Invariant: a clean run (no errors, no unknown files) produces zero ERROR-level log lines."""
import logging


def test_clean_run_has_no_error_log_lines(tmp_path, caplog, monkeypatch):
    import main
    monkeypatch.setattr(main, 'load_existing_keys', lambda p: set())
    empty_folder = tmp_path / 'input'
    empty_folder.mkdir()
    config = {
        'output': {'master_file': str(tmp_path / 'master.xlsx')},
        'processing': {'deduplicate': False},
        'smtp': {'enabled': False},
    }
    caplog.set_level(logging.DEBUG)
    main.run_local_mode(str(empty_folder), config, dry_run=True)

    error_lines = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(error_lines) == 0, \
        f"Clean run produced ERROR lines: {[r.message for r in error_lines]}"
