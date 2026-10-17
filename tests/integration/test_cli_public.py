import json
import sys

import pytest

from kjnlae.cli import _parser, main


def test_public_cli_has_only_five_commands():
    parser = _parser()
    commands = parser._subparsers._group_actions[0].choices
    assert set(commands) == {"model", "doctor", "scan", "serve"}
    assert set(commands["model"]._subparsers._group_actions[0].choices) == {"download", "verify"}


def test_scan_missing_model_is_structured_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("kjnlae.classifiers.artifacts.Path.home", lambda: tmp_path)
    monkeypatch.delenv("KJNLAE_MODEL_DIR", raising=False)
    monkeypatch.delenv("KJNLAE_MODEL_HASH", raising=False)
    with pytest.raises(SystemExit) as failure:
        main(["scan", "--text", "A public schedule."])
    assert failure.value.code == 1
    assert json.loads(capsys.readouterr().out)["detection_status"] == "INCOMPLETE"


def test_doctor_missing_model_exits_nonzero(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("kjnlae.classifiers.artifacts.Path.home", lambda: tmp_path)
    monkeypatch.delenv("KJNLAE_MODEL_DIR", raising=False)
    monkeypatch.delenv("KJNLAE_MODEL_HASH", raising=False)
    with pytest.raises(SystemExit) as failure:
        main(["doctor"])
    assert failure.value.code == 1
    assert json.loads(capsys.readouterr().out)["self_test"]["detection_status"] == "INCOMPLETE"


def test_serve_warns_when_dashboard_assets_are_missing(monkeypatch, capsys):
    monkeypatch.setattr("kjnlae.api.app.dashboard_dist", lambda: None)
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    main(["serve"])
    assert "API only" in capsys.readouterr().err


def test_serve_without_api_extra_has_actionable_error(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    with pytest.raises(SystemExit) as error:
        main(["serve"])
    assert error.value.code == 2
    assert "kjnlae[api]" in capsys.readouterr().err
