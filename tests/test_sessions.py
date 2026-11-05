import threading
import time

import pytest

from app.ingest import IngestError, IngestLimits
from app.sessions import SessionLimitError, SessionStore
from guardrails.executor import execute_safe


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture()
def clock():
    return Clock()


def store(tmp_path, clock, **kw):
    return SessionStore(tmp_path / "sessions", clock=clock, **kw)


CSV = b"name,score\nann,1\nbob,2\n"


def test_create_get_and_unguessable_ids(tmp_path, clock):
    st = store(tmp_path, clock)
    s = st.create()
    assert len(s.id) >= 30 and st.get(s.id) is s
    assert st.create().id != s.id


@pytest.mark.parametrize("bad", [None, "", "short", "../../etc/passwd", "a" * 100, "x" * 30 + "/../y", "id with spaces and more chars", "x" * 30 + "\x00"])
def test_malformed_or_unknown_ids_never_resolve(tmp_path, clock, bad):
    st = store(tmp_path, clock)
    st.create()
    assert st.get(bad) is None and st.delete(bad) is False


def test_well_formed_but_unissued_id_is_rejected(tmp_path, clock):
    assert store(tmp_path, clock).get("A" * 32) is None


def test_idle_ttl_expiry_removes_the_file(tmp_path, clock):
    st = store(tmp_path, clock, ttl_s=100)
    s = st.create()
    st.add_upload(s, "a.csv", CSV)
    assert s.path.exists()
    clock.t += 99
    assert st.get(s.id) is s                      # activity renews the idle timer
    clock.t += 99
    assert st.get(s.id) is s
    clock.t += 101
    assert st.get(s.id) is None and not s.path.exists() and len(st) == 0


def test_absolute_max_age_even_if_always_active(tmp_path, clock):
    st = store(tmp_path, clock, ttl_s=100, max_age_s=250)
    s = st.create()
    st.add_upload(s, "a.csv", CSV)
    for _ in range(2):
        clock.t += 90
        assert st.get(s.id) is s
    clock.t += 90
    assert st.get(s.id) is None and not s.path.exists()


def test_cleanup_sweeps_expired_sessions_only(tmp_path, clock):
    st = store(tmp_path, clock, ttl_s=100)
    old, fresh = st.create(), None
    st.add_upload(old, "a.csv", CSV)
    clock.t += 90
    fresh = st.create()
    st.add_upload(fresh, "b.csv", CSV)
    clock.t += 20
    assert st.cleanup() == 1 and not old.path.exists() and fresh.path.exists() and len(st) == 1


def test_capacity_cap_frees_expired_sessions_first(tmp_path, clock):
    st = store(tmp_path, clock, ttl_s=100, max_sessions=2)
    st.create(), st.create()
    with pytest.raises(SessionLimitError, match="capacity"):
        st.create()
    clock.t += 200
    assert st.create() is not None                # the two expired ones were swept to make room


def test_delete_removes_data_immediately(tmp_path, clock):
    st = store(tmp_path, clock)
    s = st.create()
    st.add_upload(s, "a.csv", CSV)
    assert st.delete(s.id) and not s.path.exists() and st.get(s.id) is None and st.delete(s.id) is False


ORPHAN = "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MA"          # session-id shaped (what token_urlsafe(24) produces)


def test_startup_purges_orphans_from_a_previous_process(tmp_path, clock):
    root = tmp_path / "sessions"
    root.mkdir()
    (root / f"{ORPHAN}.sqlite").write_bytes(b"x")
    (root / f"{ORPHAN}.sqlite-journal").write_bytes(b"x")
    (root / "keep.txt").write_text("not ours")
    SessionStore(root, clock=clock)
    assert not (root / f"{ORPHAN}.sqlite").exists() and not (root / f"{ORPHAN}.sqlite-journal").exists() and (root / "keep.txt").exists()


def test_purge_never_touches_databases_that_are_not_session_files(tmp_path, clock):
    root = tmp_path / "misconfigured"          # e.g. SESSION_DIR accidentally pointed at the folder with chinook.sqlite
    root.mkdir()
    (root / "chinook.sqlite").write_bytes(b"precious")
    (root / "notes.sqlite-wal").write_bytes(b"precious")
    SessionStore(root, clock=clock)
    assert (root / "chinook.sqlite").read_bytes() == b"precious" and (root / "notes.sqlite-wal").exists()


def test_limit_errors_carry_an_http_status(tmp_path, clock):
    st = store(tmp_path, clock, max_sessions=1)
    s = st.create()
    with pytest.raises(SessionLimitError) as cap:
        st.create()
    assert cap.value.status == 503
    st2 = store(tmp_path / "b", clock, max_uploads=1)
    s2 = st2.create()
    st2.add_upload(s2, "a.csv", CSV)
    with pytest.raises(SessionLimitError) as per:
        st2.add_upload(s2, "b.csv", CSV)
    assert per.value.status == 429 and s


def test_table_cap_rejects_the_upload_and_leaves_nothing_behind(tmp_path, clock):
    st = store(tmp_path, clock, max_tables=2)
    s = st.create()
    st.add_upload(s, "a.csv", CSV)
    st.add_upload(s, "b.csv", CSV)
    with pytest.raises(SessionLimitError, match="tables"):
        st.add_upload(s, "c.csv", CSV)
    assert s.table_names == {"a", "b"}
    assert execute_safe(s.path, "SELECT COUNT(*) FROM a", s.table_names).ok
    assert not execute_safe(s.path, "SELECT COUNT(*) FROM c", {"a", "b", "c"}).ok       # the rejected table was dropped from the file


def test_upload_count_cap(tmp_path, clock):
    st = store(tmp_path, clock, max_tables=9, max_uploads=2)
    s = st.create()
    st.add_upload(s, "a.csv", CSV)
    st.add_upload(s, "b.csv", CSV)
    with pytest.raises(SessionLimitError, match="uploads"):
        st.add_upload(s, "c.csv", CSV)


def test_failed_upload_does_not_change_the_session(tmp_path, clock):
    st = store(tmp_path, clock, limits=IngestLimits(max_rows=2))
    s = st.create()
    with pytest.raises(IngestError):
        st.add_upload(s, "big.csv", b"a\n1\n2\n3\n4\n")
    assert s.tables == [] and s.uploads == 0
    st.add_upload(s, "ok.csv", b"a\n1\n")
    assert s.table_names == {"ok"}


def test_sessions_cannot_see_each_others_data(tmp_path, clock):
    st = store(tmp_path, clock)
    a, b = st.create(), st.create()
    st.add_upload(a, "secret_a.csv", b"password\nhunter2\n")
    st.add_upload(b, "other_b.csv", b"x\n1\n")
    assert a.path != b.path
    own = execute_safe(a.path, "SELECT * FROM secret_a", a.table_names)
    assert own.ok and own.rows == [("hunter2",)]
    cross = execute_safe(b.path, "SELECT * FROM secret_a", b.table_names)
    assert not cross.ok and cross.code == "forbidden_table"
    attach = execute_safe(b.path, f"ATTACH DATABASE '{a.path}' AS stolen", b.table_names)
    assert not attach.ok and attach.code == "not_select"
    sneaky = execute_safe(b.path, f"SELECT * FROM '{a.path}'", b.table_names)
    assert not sneaky.ok


def test_seconds_left_reflects_both_timers(tmp_path, clock):
    st = store(tmp_path, clock, ttl_s=100, max_age_s=150)
    s = st.create()
    assert st.seconds_left(s) == 100
    clock.t += 80
    st.get(s.id)
    clock.t += 50
    assert st.seconds_left(s) == 20               # the absolute age (150 - 130) is the tighter limit


def test_sweeper_thread_removes_expired_sessions_and_stops_cleanly(tmp_path):
    real = {"t": time.time()}
    st = SessionStore(tmp_path / "s", ttl_s=1, clock=lambda: real["t"])
    s = st.create()
    st.add_upload(s, "a.csv", CSV)
    real["t"] += 5
    st.start_sweeper(interval_s=0.05)
    for _ in range(100):
        if not s.path.exists():
            break
        time.sleep(0.02)
    st.stop_sweeper()
    assert not s.path.exists() and len(st) == 0
    assert threading.active_count() >= 1


def test_status_polling_does_not_extend_the_idle_timer(tmp_path, clock):
    st = store(tmp_path, clock, ttl_s=100)
    s = st.create()
    clock.t += 90
    assert st.get(s.id, touch=False) is s       # a status poll
    clock.t += 20
    assert st.get(s.id) is None                 # idle time still counted from creation, so it has expired
