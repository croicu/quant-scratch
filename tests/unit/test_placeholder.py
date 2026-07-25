from __package_name__.cli import main


def test_main_runs_clean(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    exit_code = main([])
    assert exit_code == 0
