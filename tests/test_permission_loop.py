"""Permission regressions use temporary settings/stores/DBs; no model calls."""
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import dispatcher as D
import perm_store as P


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / '.claude').mkdir()
    (tmp_path / '.claude/settings.json').write_text(json.dumps({'permissions': {'deny': ['Bash(sqlite3 *)']}}))
    monkeypatch.setenv('QRL_LAB_DIR', str(tmp_path))
    monkeypatch.setenv('QRL_DISPATCH_DB', str(tmp_path / '.lab/dispatch.db'))
    return str(tmp_path)


def test_deny_composites_and_positive_control(root):
    for cmd in ['sqlite3 db', 'sqlite3', 'cat x; sqlite3 db .tables', 'cat x && sqlite3 db',
                'cat x\nsqlite3 db', 'echo $(sqlite3 db)', 'sqlite3 db | cat']:
        assert P.deny_rule('Bash', {'command': cmd}, root)
        assert P.create('Bash', {'command': cmd}, root=root) is None
    assert P.create('Bash', {'command': 'ls /etc'}, root=root)
    assert len(P.pending(root)) == 1


def test_parallel_duplicates_and_just_answered(root):
    def create(_):
        return P.create('Bash', {'command': 'ls /etc'}, source='headless', root=root)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(create, range(24)))
    assert len(set(ids)) == 1
    assert P.decide(ids[0], True, root=root)
    P.mark_delivered(ids[0], root)
    assert create(None) == ids[0]
    assert P.undelivered_answers(root) == []


def legacy(root, state='pending', cmd='sqlite3 db'):
    rid = 'legacy-' + str(time.time_ns())
    P._write({'id': rid, 'ts': time.time(), 'source': 'headless', 'thread_id': '', 'tool': 'Bash',
              'detail': cmd, 'state': state, 'delivered': False}, root)
    return rid


def test_legacy_approve_never_wakes_job(root):
    rid = legacy(root)
    assert P.decide(rid, True, root=root)
    d = D.Dispatcher(root)
    try:
        assert not [i for i in d._candidates() if i['kind'] == 'perm_answer']
        assert P.read(rid, root)['state'] == 'withdrawn_deny_rule'
        assert P.take_approval('Bash', {'command': 'sqlite3 db'}, root) is None
        assert P.create('Bash', {'command': 'sqlite3 db'}, root=root) is None
    finally:
        d.close()


def test_startup_withdraws_pending_without_job(root):
    rid = legacy(root)
    d = D.Dispatcher(root)
    try:
        d.recover()
        assert P.read(rid, root)['state'] == 'withdrawn_deny_rule'
        assert not d.work.active()
        assert not P.pending(root)
    finally:
        d.close()


def test_batches_by_thread_active_guard_and_debounce(root):
    d = D.Dispatcher(root)
    try:
        tid = d.lab.researcher_send('test')
        d.lab.set_status(tid, 'done')
        ids = [P.create('Bash', {'command': f'ls /tmp/{n}'}, root=root, source='headless', thread_id=tid)
               for n in range(2)]
        for rid in ids:
            P.decide(rid, True, root=root)
        items = [i for i in d._candidates() if i['kind'] == 'perm_answer']
        assert len(items) == 1 and set(items[0]['perm_ids']) == set(ids)
        assert D.item_key(items[0]) == D.item_key(dict(items[0], perm_ids=['other']))
        jid = d.work.create('worker', 'perm_answer', 'test', thread_id=tid, status='running')
        assert not [i for i in d._candidates() if i['kind'] == 'perm_answer']
        d.work.set_status(jid, 'done')
        d.dd.conn.execute("INSERT INTO settings VALUES (?,?,?,?)",
                          ('perm_last_wake:' + tid, str(time.time()), D.now_iso(), 'test'))
        assert not [i for i in d._candidates() if i['kind'] == 'perm_answer']
    finally:
        d.close()


def test_finish_deny_reports_rule_once_no_card(root, monkeypatch):
    d = D.Dispatcher(root)
    posts = []
    monkeypatch.setattr(d, '_post', lambda *a, **k: posts.append(a[1]))
    monkeypatch.setattr(d, '_journal', lambda *a: None)
    res = D._empty_result()
    res.update(text='test', duration_s=0, denials=[{'tool_name': 'Bash', 'tool_input': {'command': 'sqlite3 db'}}] * 2)
    item = dict(kind='perm_answer', thread_id='t', reply_to='t', msg_ids=[], req_ids=[])
    try:
        d._finish_ok('claude', item, res)
        assert not P.pending(root)
        assert posts[0].count('Bash(sqlite3 *)') == 1
    finally:
        d.close()


def test_hook_deny_is_immediate_and_never_reuses_answer(root):
    import perm_hook
    raw = json.dumps({'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash',
                      'tool_input': {'command': 'sqlite3 db'}})
    res = perm_hook.handle(raw, root=root, sleep=lambda _: pytest.fail('deny must not wait'))
    assert res['hookSpecificOutput']['decision']['behavior'] == 'deny'
    assert not P.pending(root)
    rid = P.create('Bash', {'command': 'echo allowed'}, root=root)
    P.decide(rid, True, root=root)
    fresh = P.create('Bash', {'command': 'echo allowed'}, root=root)
    assert fresh != rid


def test_distinct_long_commands_do_not_merge(root):
    prefix = 'echo ' + 'x' * P.MAX_DETAIL
    one = P.create('Bash', {'command': prefix + 'a'}, root=root, source='headless')
    two = P.create('Bash', {'command': prefix + 'b'}, root=root, source='headless')
    assert one != two


def test_full_approval_fingerprint_and_legacy_truncation(root):
    prefix = 'echo ' + 'x' * P.MAX_DETAIL
    cmd = prefix + 'a'
    rid = P.create('Bash', {'command': cmd}, root=root, source='headless')
    assert P.decide(rid, True, root=root)
    assert P.take_approval('Bash', {'command': prefix + 'b'}, root) is None
    assert P.take_approval('Bash', {'command': cmd}, root) == rid
    assert P.take_approval('Bash', {'command': cmd}, root) is None
    old = legacy(root, 'approved', prefix[:P.MAX_DETAIL])
    rec = P.read(old, root)
    rec['decided_at'] = time.time()
    P._write(rec, root)
    assert P.take_approval('Bash', {'command': prefix[:P.MAX_DETAIL]}, root) is None
