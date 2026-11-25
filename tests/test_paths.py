from coding_tutor import paths


def test_repo_or_cwd_prefers_the_repository_folder(tmp_path):
    repo, cwd = tmp_path / "repo", tmp_path / "task"
    (repo / "schemas").mkdir(parents=True)
    assert paths.repo_or_cwd("schemas", repo, cwd) == repo / "schemas"


def test_repo_or_cwd_falls_back_to_the_working_directory(tmp_path):
    # An installed package (e.g. on Vercel) has no repository folder next to it.
    repo, cwd = tmp_path / "site-packages", tmp_path / "task"
    assert paths.repo_or_cwd("schemas", repo, cwd) == cwd / "schemas"


def test_repo_or_cwd_ignores_a_file_with_the_folder_name(tmp_path):
    repo, cwd = tmp_path / "repo", tmp_path / "task"
    repo.mkdir()
    (repo / "schemas").write_text("not a folder", encoding="utf-8")
    assert paths.repo_or_cwd("schemas", repo, cwd) == cwd / "schemas"


def test_repo_or_cwd_defaults_to_the_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert paths.repo_or_cwd("no-such-folder", tmp_path / "missing") == tmp_path / "no-such-folder"


def test_this_checkout_uses_its_own_folders():
    assert paths.SCHEMAS_DIR == paths.REPO_ROOT / "schemas"
    assert paths.CONTENT_DIR == paths.REPO_ROOT / "content"
