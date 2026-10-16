from pathlib import Path

from app import workspace
from app.db import now


def registered_file(db, task="t_expired", name="notes.txt"):
    folder = workspace.task_dir("u_retention", task, "study")
    path = folder / "out" / name
    path.write_text("private notes")
    record = workspace.register(db, "u_retention", task, path, "txt", "free")
    return path, record


def expire(db, record):
    db.run("UPDATE workspace_files SET delete_after=? WHERE id=?", (now() - 1, record["id"]))


def test_expiry_removes_actual_task_file_without_touching_same_named_user_path(db):
    path, record = registered_file(db)
    decoy = workspace.user_root("u_retention") / "out" / "notes.txt"
    decoy.parent.mkdir()
    decoy.write_text("unrelated file")
    expire(db, record)

    assert workspace.purge_expired(db) == 1
    assert not path.exists()
    assert decoy.read_text() == "unrelated file"
    assert db.one("SELECT id FROM workspace_files WHERE id=?", (record["id"],)) is None
    assert workspace.usage_bytes(db, "u_retention") == 0


def test_failed_deletion_keeps_record_and_retries_on_next_run(db, monkeypatch):
    path, record = registered_file(db)
    expire(db, record)
    unlink = Path.unlink

    def deny_unlink(target, *args, **kwargs):
        if target == path:
            raise PermissionError("temporarily unavailable")
        return unlink(target, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", deny_unlink)
        assert workspace.purge_expired(db) == 0
    assert path.exists()
    assert db.one("SELECT id FROM workspace_files WHERE id=?", (record["id"],))
    assert workspace.purge_expired(db) == 1
    assert not path.exists()


def test_expired_registration_does_not_delete_file_with_retained_version(db):
    path, old_record = registered_file(db)
    new_record = workspace.register(db, "u_retention", "t_expired", path, "txt", "free")
    expire(db, old_record)

    assert workspace.purge_expired(db) == 1
    assert path.exists()
    assert db.one("SELECT id FROM workspace_files WHERE id=?", (new_record["id"],))


def test_expiry_refuses_symlink_outside_owner_workspace(db, tmp_path):
    path, record = registered_file(db)
    outside = tmp_path / "another-users-notes.txt"
    outside.write_text("keep private")
    path.unlink()
    path.symlink_to(outside)
    expire(db, record)

    assert workspace.purge_expired(db) == 0
    assert outside.read_text() == "keep private"
    assert db.one("SELECT id FROM workspace_files WHERE id=?", (record["id"],))
