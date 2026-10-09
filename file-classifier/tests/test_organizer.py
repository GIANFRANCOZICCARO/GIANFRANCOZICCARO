from pathlib import Path

from file_classifier.db import FileDatabase
from file_classifier.paths import path_key
from file_classifier.organizer import build_plan, execute_plan


def _setup_db(tmp_path: Path, source_dir: Path) -> FileDatabase:
    db = FileDatabase(tmp_path / "test.db")
    for name, theme, content in [
        ("a.txt", "cucina", "ricetta"),
        ("b.txt", "cucina", "altra ricetta"),
        ("c.txt", "finanza", "fattura"),
    ]:
        path = source_dir / name
        path.write_text(content, encoding="utf-8")
        fid = db.upsert_file(
            filename=name, original_path=str(path), current_path=str(path),
            extension=".txt", size_bytes=path.stat().st_size, modified_at="t",
            content_hash="h", content=content, extraction_error=None,
        )
        db.set_theme(fid, theme, [theme])
    return db


def test_dry_run_does_not_touch_filesystem(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"

    with _setup_db(tmp_path, source_dir) as db:
        plan = build_plan(db, dest_dir)
        assert len(plan) == 3
        execute_plan(db, plan, mode="copy", dry_run=True)
        assert not dest_dir.exists()


def test_copy_organizes_by_theme(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"

    with _setup_db(tmp_path, source_dir) as db:
        plan = build_plan(db, dest_dir)
        execute_plan(db, plan, mode="copy", dry_run=False)

        assert (dest_dir / "cucina" / "a.txt").exists()
        assert (dest_dir / "cucina" / "b.txt").exists()
        assert (dest_dir / "finanza" / "c.txt").exists()
        # I file originali restano al loro posto con mode=copy.
        assert (source_dir / "a.txt").exists()


def test_move_updates_current_path_in_db(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"

    with _setup_db(tmp_path, source_dir) as db:
        plan = build_plan(db, dest_dir)
        executed = execute_plan(db, plan, mode="move", dry_run=False)

        assert not (source_dir / "a.txt").exists()
        assert (dest_dir / "cucina" / "a.txt").exists()

        for item in executed:
            record = db.get_file(item.file_id)
            assert path_key(record.current_path) == path_key(item.destination)


def test_dedupe_on_name_collision(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"

    with FileDatabase(tmp_path / "test.db") as db:
        for i in range(2):
            sub = source_dir / str(i)
            sub.mkdir()
            path = sub / "same.txt"
            path.write_text(f"contenuto {i}", encoding="utf-8")
            fid = db.upsert_file(
                filename="same.txt", original_path=str(path), current_path=str(path),
                extension=".txt", size_bytes=path.stat().st_size, modified_at="t",
                content_hash=f"h{i}", content=f"contenuto {i}", extraction_error=None,
            )
            db.set_theme(fid, "tema", ["tema"])

        plan = build_plan(db, dest_dir)
        destinations = {str(item.destination) for item in plan}
        assert len(destinations) == 2
