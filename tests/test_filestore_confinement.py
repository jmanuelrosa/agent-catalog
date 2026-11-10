import importlib.util
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from catalog_tree import SKILLS


class BridgeError(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    fastapi = SimpleNamespace(
        FastAPI=lambda **kwargs: SimpleNamespace(get=lambda route: lambda function: function),
        HTTPException=BridgeError,
        Query=lambda default=None, **kwargs: default,
        status=SimpleNamespace(
            HTTP_400_BAD_REQUEST=400,
            HTTP_403_FORBIDDEN=403,
            HTTP_404_NOT_FOUND=404,
        ),
    )
    monkeypatch.setitem(sys.modules, "fastapi", fastapi)
    path = SKILLS / "google-cloud-filestore-nfs-browser/scripts/bridge_server/main.py"
    spec = importlib.util.spec_from_file_location("filestore_bridge_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mount = tmp_path / "share"
    mount.mkdir()
    monkeypatch.setattr(module, "MOUNT_ROOT", str(mount))
    return module, mount


@pytest.fixture
def jump_host():
    path = SKILLS / "google-cloud-filestore-nfs-browser/scripts/jump_host_engine.py"
    spec = importlib.util.spec_from_file_location("filestore_jump_host_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_jump_operation(module, operation, mount, path):
    if operation == "tree":
        script = module._build_remote_tree_script(str(mount), path, 2, 10)
    else:
        script = module._build_remote_search_script(str(mount), path, None, "marker", 10)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize("operation", ["tree", "search"])
@pytest.mark.parametrize("escape", ["parent", "directory-link"])
def test_jump_operations_reject_outside_roots(jump_host, tmp_path, operation, escape):
    mount = tmp_path / "share"
    mount.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("outside marker\n")
    if escape == "parent":
        path = "../outside"
    else:
        (mount / "escape").symlink_to(outside, target_is_directory=True)
        path = "escape"
    result = run_jump_operation(jump_host, operation, mount, path)
    assert result.get("error") == "Access denied: path traversal"


@pytest.mark.parametrize("operation", ["tree", "search"])
def test_jump_operations_do_not_follow_outside_file_links(jump_host, tmp_path, operation):
    mount = tmp_path / "share"
    mount.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside marker\n")
    (mount / "escape.txt").symlink_to(outside)
    result = run_jump_operation(jump_host, operation, mount, "/")
    assert result["entries" if operation == "tree" else "matches"] == []


def test_search_reads_regular_share_files(bridge):
    module, mount = bridge
    (mount / "inside.txt").write_text("inside marker\n")
    result = module.search_files(path="/", pattern=None, grep="marker", max_results=10)
    assert result == {
        "matches": [{"file": "/inside.txt", "line": 1, "content": "inside marker"}],
    }


def test_search_does_not_read_file_symlinks_outside_share(bridge, tmp_path):
    module, mount = bridge
    outside = tmp_path / "outside.txt"
    outside.write_text("outside marker\n")
    (mount / "escape.txt").symlink_to(outside)
    result = module.search_files(path="/", pattern=None, grep="marker", max_results=10)
    assert result == {"matches": []}


def test_tree_does_not_stat_file_symlinks_outside_share(bridge, tmp_path):
    module, mount = bridge
    outside = tmp_path / "outside.txt"
    outside.write_text("outside marker\n")
    (mount / "escape.txt").symlink_to(outside)
    result = module.list_tree(path="/", depth=2, max_entries=10)
    assert result["entries"] == []


def test_search_keeps_file_symlinks_inside_share(bridge):
    module, mount = bridge
    target = mount / "inside.txt"
    target.write_text("inside marker\n")
    (mount / "alias.txt").symlink_to(target)
    result = module.search_files(path="/", pattern="alias.txt", grep="marker", max_results=10)
    assert result == {
        "matches": [{"file": "/alias.txt", "line": 1, "content": "inside marker"}],
    }


def test_search_rejects_directory_swap_during_open(bridge, tmp_path, monkeypatch):
    module, mount = bridge
    directory = mount / "nested"
    directory.mkdir()
    (directory / "inside.txt").write_text("inside marker\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "inside.txt").write_text("outside marker\n")
    original_open = module.os.open
    swapped = False

    def swap_directory(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "nested" and not swapped:
            directory.rename(mount / "original")
            directory.symlink_to(outside, target_is_directory=True)
            swapped = True
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", swap_directory)
    result = module.search_files(path="/", pattern=None, grep="marker", max_results=10)
    assert swapped
    assert result == {"matches": []}


def test_read_rejects_file_swap_during_open(bridge, tmp_path, monkeypatch):
    module, mount = bridge
    target = mount / "inside.txt"
    target.write_text("inside marker\n")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside marker\n")
    original_open = module.os.open
    swapped = False

    def swap_file(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "inside.txt" and not swapped:
            target.unlink()
            target.symlink_to(outside)
            swapped = True
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", swap_file)
    with pytest.raises(BridgeError) as error:
        module.read_file(path="/inside.txt", head=1, tail=None, start_line=None, end_line=None)
    assert swapped
    assert error.value.status_code == 403


def test_read_reports_binary_file_metadata(bridge):
    module, mount = bridge
    content = b"binary\x00marker"
    (mount / "binary.bin").write_bytes(content)
    result = module.read_file(path="/binary.bin", head=1, tail=None, start_line=None, end_line=None)
    assert result["is_binary"] is True
    assert result["size_bytes"] == len(content)


def test_read_rejects_file_symlinks_outside_share(bridge, tmp_path):
    module, mount = bridge
    outside = tmp_path / "outside.txt"
    outside.write_text("outside marker\n")
    (mount / "escape.txt").symlink_to(outside)
    with pytest.raises(BridgeError) as error:
        module.read_file(path="/escape.txt", head=1, tail=None, start_line=None, end_line=None)
    assert error.value.status_code == 403
