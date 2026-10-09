import json
import ntpath
from pathlib import Path

import pytest

from file_classifier.cli import main
from file_classifier.db import FileDatabase
from file_classifier.organizer import OrganizePlan, build_plan, execute_plan
from file_classifier.classifier import classify_files
from file_classifier import paths


def insert(db, path):
    fid = db.upsert_file(filename=path.name, original_path=str(path), current_path=str(path),
                        extension='.txt', size_bytes=1, modified_at='t', content_hash='h',
                        content='testo', extraction_error=None)
    db.set_theme(fid, 'tema', ['tema'])
    return fid


def test_upsert_id_after_other_insert_and_alias(tmp_path):
    a, b = tmp_path / 'a.txt', tmp_path / 'b.txt'
    a.write_text('a'); b.write_text('b')
    with FileDatabase(tmp_path / 'test.db') as db:
        aid = insert(db, a)
        insert(db, b)
        alias = tmp_path / 'folder' / '..' / 'a.txt'
        assert insert(db, alias) == aid
        assert len(db.all_files()) == 2


@pytest.mark.parametrize('nested', [False, True])
def test_destination_inside_scan_root(tmp_path, nested):
    root = tmp_path / 'source'; root.mkdir()
    a = root / 'a.txt'; a.write_text('a')
    with FileDatabase(tmp_path / 'test.db') as db:
        insert(db, a); db.add_scan_root(root)
        with pytest.raises(ValueError):
            build_plan(db, root / 'output' if nested else root)
        assert a.read_text() == 'a'


def test_existing_collisions_and_broken_link(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    a = source / 'same.txt'; a.write_text('new')
    theme = tmp_path / 'out' / 'tema'; theme.mkdir(parents=True)
    (theme / 'same.txt').write_text('old')
    (theme / 'same_1.txt').write_text('older')
    with FileDatabase(tmp_path / 'test.db') as db:
        insert(db, a)
        plan = build_plan(db, theme.parent)
        assert plan[0].destination.name == 'same_2.txt'
        execute_plan(db, plan, dry_run=False)
        assert (theme / 'same.txt').read_text() == 'old'
        assert (theme / 'same_1.txt').read_text() == 'older'
        assert (theme / 'same_2.txt').read_text() == 'new'


@pytest.mark.parametrize('mode', ['copy', 'move'])
def test_collision_after_planning_keeps_source_and_db(tmp_path, mode):
    a = tmp_path / 'a.txt'; a.write_text('new')
    with FileDatabase(tmp_path / 'test.db') as db:
        fid = insert(db, a)
        plan = build_plan(db, tmp_path.parent / (tmp_path.name + '_out'))
        dest = plan[0].destination; dest.parent.mkdir(parents=True)
        dest.write_text('existing')
        with pytest.raises(FileExistsError):
            execute_plan(db, plan, mode=mode, dry_run=False)
        assert dest.read_text() == 'existing'
        assert a.read_text() == 'new'
        assert paths.path_key(db.get_file(fid).current_path) == paths.path_key(a)


@pytest.mark.parametrize('mode', ['copy', 'move'])
def test_paths_and_search_after_organization_and_reindex(tmp_path, mode):
    root = tmp_path / 'source'; root.mkdir()
    a = root / 'a.txt'; a.write_text('testo')
    with FileDatabase(tmp_path / 'test.db') as db:
        fid = insert(db, a)
        plan = build_plan(db, tmp_path / 'out')
        execute_plan(db, plan, mode=mode, dry_run=False)
        dest = plan[0].destination
        record = db.get_file(fid)
        assert paths.path_key(record.original_path) == paths.path_key(a)
        assert paths.path_key(record.current_path) == paths.path_key(dest)
        assert record.organized_at
        assert paths.path_key(db.search('testo')[0]['current_path']) == paths.path_key(dest)
        assert insert(db, dest) == fid
        if mode == 'copy':
            assert insert(db, a) == fid
            assert paths.path_key(db.get_file(fid).current_path) == paths.path_key(dest)
        assert len(db.all_files()) == 1
        assert build_plan(db, tmp_path / 'out') == []


@pytest.mark.parametrize('kind', ['same', 'duplicate_source', 'duplicate_destination'])
def test_invalid_plan_is_rejected_before_mutation(tmp_path, kind):
    a, b, dest = tmp_path / 'a', tmp_path / 'b', tmp_path / 'out'
    a.write_text('a'); b.write_text('b')
    with FileDatabase(tmp_path / 'test.db') as db:
        aid, bid = insert(db, a), insert(db, b)
        if kind == 'same':
            plan = [OrganizePlan(aid, a, a)]
        elif kind == 'duplicate_source':
            plan = [OrganizePlan(aid, a, dest), OrganizePlan(aid, a, tmp_path / 'other')]
        else:
            plan = [OrganizePlan(aid, a, dest), OrganizePlan(bid, b, dest)]
        with pytest.raises(ValueError):
            execute_plan(db, plan, dry_run=False)
        assert not dest.exists()
        assert a.exists() and b.exists()


def test_windows_normalization(monkeypatch):
    monkeypatch.setattr(paths.os.path, 'normcase', ntpath.normcase)
    assert paths.path_key(Path('Example.TXT')) == paths.path_key(Path('example.txt'))


def test_index_progress_and_database_exclusion(tmp_path, capsys):
    (tmp_path / 'a.txt').write_text('testo')
    (tmp_path / 'b.bin').write_bytes(b'abc')
    dbpath = tmp_path / 'index.db'
    assert main(['--db', str(dbpath), 'index', str(tmp_path)]) == 0
    output = capsys.readouterr()
    events = [json.loads(line) for line in output.err.splitlines()]
    assert events[0]['event'] == 'start'
    assert events[-1] == dict(event='complete', indexed=2, skipped=0, metadata_only=1, path=None)
    assert sum(e['event'] == 'processing' for e in events) == 2
    with FileDatabase(dbpath) as db:
        assert len(db.all_files()) == 2


def test_empty_vocabulary(tmp_path):
    with FileDatabase(tmp_path / 'test.db') as db:
        for name in ('a.txt', 'b.txt'):
            p = tmp_path / name; p.write_text('il la di')
            fid = insert(db, p)
            db._conn.execute('UPDATE files SET content=? WHERE id=?', ('il la di', fid))
        assert all(r.theme == 'generico' for r in classify_files(db.all_files()))


def test_exclusive_creation_handles_race(tmp_path, monkeypatch):
    a = tmp_path / 'source' / 'a.txt'; a.parent.mkdir(); a.write_text('source')
    with FileDatabase(tmp_path / 'test.db') as db:
        fid = insert(db, a)
        plan = build_plan(db, tmp_path / 'out')
        destination = plan[0].destination
        original_open = Path.open
        def race_open(path, mode='r', *args, **kwargs):
            if path == destination and mode == 'xb':
                with original_open(path, 'w') as target:
                    target.write('concurrent')
            return original_open(path, mode, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', race_open)
        with pytest.raises(FileExistsError):
            execute_plan(db, plan, mode='move', dry_run=False)
        assert destination.read_text() == 'concurrent'
        assert a.read_text() == 'source'
        assert paths.path_key(db.get_file(fid).current_path) == paths.path_key(a)


def test_dry_run_preserves_db(tmp_path):
    a = tmp_path / 'source' / 'a.txt'; a.parent.mkdir(); a.write_text('source')
    with FileDatabase(tmp_path / 'test.db') as db:
        fid = insert(db, a)
        before = db.get_file(fid)
        execute_plan(db, build_plan(db, tmp_path / 'out'))
        assert db.get_file(fid) == before
        assert not (tmp_path / 'out').exists()


@pytest.mark.skipif(__import__('os').name != 'nt', reason='Filesystem Windows richiesto')
def test_windows_case_alias_and_destination_collision(tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    a = root / 'Report.txt'; a.write_text('new')
    out = tmp_path / 'out' / 'tema'; out.mkdir(parents=True)
    (out / 'REPORT.TXT').write_text('existing')
    with FileDatabase(tmp_path / 'test.db') as db:
        fid = insert(db, a)
        assert insert(db, root / 'REPORT.TXT') == fid
        plan = build_plan(db, out.parent)
        assert plan[0].destination.name == 'REPORT_1.TXT'
        execute_plan(db, plan, dry_run=False)
        assert (out / 'REPORT.TXT').read_text() == 'existing'
        assert len(db.all_files()) == 1
