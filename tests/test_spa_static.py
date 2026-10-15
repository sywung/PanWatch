"""前端靜態檔服務：index.html 等「入口檔」必須每次向伺服器驗證（Cache-Control: no-cache），
否則瀏覽器會憑 Last-Modified 啟發式快取，更新後使用者仍在跑舊版 JS（2026-10-15 實際發生）。
同時不得讓 path 跳出 static 目錄。"""
import os

import pytest

from src.web.spa import spa_file_response


@pytest.fixture()
def static_dir(tmp_path):
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>index</html>")
    (root / "sw.js").write_text("// sw")
    (root / "manifest.json").write_text("{}")
    (root / "manifest.zh-TW.json").write_text("{}")
    (root / "icon-192.png").write_bytes(b"png")
    (root / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("secret")
    return str(root)


def _cache_control(response) -> str:
    return response.headers.get("cache-control", "")


@pytest.mark.parametrize("path", ["", "index.html", "portfolio", "stocks/2330", "no/such/route"])
def test_entry_and_spa_routes_serve_index_with_no_cache(static_dir, path):
    response = spa_file_response(static_dir, path)
    assert os.path.samefile(response.path, os.path.join(static_dir, "index.html"))
    assert _cache_control(response) == "no-cache"


@pytest.mark.parametrize("path", ["sw.js", "manifest.json", "manifest.zh-TW.json"])
def test_service_worker_and_manifests_revalidate(static_dir, path):
    response = spa_file_response(static_dir, path)
    assert os.path.samefile(response.path, os.path.join(static_dir, path))
    assert _cache_control(response) == "no-cache"


def test_hashed_assets_are_served_but_not_marked_no_cache(static_dir):
    response = spa_file_response(static_dir, "assets/index-abc123.js")
    assert os.path.samefile(response.path, os.path.join(static_dir, "assets", "index-abc123.js"))
    assert "no-cache" not in _cache_control(response)


def test_other_static_files_are_served_unchanged(static_dir):
    response = spa_file_response(static_dir, "icon-192.png")
    assert os.path.samefile(response.path, os.path.join(static_dir, "icon-192.png"))
    assert "no-cache" not in _cache_control(response)


@pytest.mark.parametrize("path", ["../secret.txt", "assets/../../secret.txt", "/etc/hosts", "..%2fsecret.txt"])
def test_path_cannot_escape_static_dir(static_dir, path):
    response = spa_file_response(static_dir, path)
    assert os.path.samefile(response.path, os.path.join(static_dir, "index.html"))
    assert _cache_control(response) == "no-cache"


def test_directory_path_falls_back_to_index(static_dir):
    response = spa_file_response(static_dir, "assets")
    assert os.path.samefile(response.path, os.path.join(static_dir, "index.html"))
