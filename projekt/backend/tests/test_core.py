import asyncio
import csv
import io
import sqlite3

import pytest
from backend.analysis import datasets, experiments, report
from backend.core import Config, Engine, Store, csv_export, extract, normalize, sqlite_export

pytestmark = pytest.mark.asyncio


async def test_graph_thresholds_metadata_cycles(crawl, store, site):
    run_id = await crawl(strategy="bfs")
    metrics = store.metrics(run_id)
    assert metrics["qualifies"] and metrics["subpages"] >= 20 and metrics["depth"] == 3
    assert metrics["failures"] == 1
    graph = store.graph(run_id)
    root = next(n for n in graph["nodes"] if n["url"] == site[0]+"/")
    assert root["outgoing"] > root["unique_targets"]
    assert root["keywords"] == 'sieć, "Łódź"'
    assert "bad hidden" not in root["body"]
    assert len([r for r in store.records(run_id) if r["url"] == site[0]+"/p/1"]) == 1
    assert next(n for n in graph["nodes"] if n["url"].endswith('/blocked'))["status"] == 'robots'


@pytest.mark.parametrize("strategy,expected",[("bfs",['/order','/a','/b','/aa']),("dfs",['/order','/a','/aa','/b'])])
async def test_traversal_order(strategy, expected, crawl, store, site):
    run_id = await crawl(url=site[0]+"/order",strategy=strategy)
    assert [r["url"].replace(site[0],"") for r in store.records(run_id)] == expected


@pytest.mark.parametrize("mode,resources",[("hyperlinks",0),("images",1),("all",3)])
async def test_link_modes(mode, resources, crawl, store):
    run_id = await crawl(links=mode)
    assert store.metrics(run_id)["resources"] == resources


async def test_scope_depth_and_binary(crawl, store, site):
    local = await crawl(depth=1,links="all")
    assert not any(r["url"].startswith(site[1]) for r in store.records(local))
    assert not any(r["url"].endswith('/level2') for r in store.records(local))
    global_run = await crawl(depth=1,scope="web")
    assert any(r["url"] == site[1]+"/external" and r["status"] == 'ok' for r in store.records(global_run))
    assert store.metrics(local)["truncated"]


async def test_redirect_scope_robots(crawl, store, site):
    for suffix, status in [("/redirect-external","scope"),("/redirect-blocked","robots")]:
        run_id = await crawl(url=site[0]+suffix)
        assert store.records(run_id)[0]["status"] == status
    run_id = await crawl(url=site[0]+"/redirect")
    assert store.records(run_id)[0]["final_url"] == site[0]+"/p/2"


async def test_redirect_deduplicates_fetch(crawl, store, site):
    before = len(site[2])
    run_id = await crawl(strategy='bfs')
    assert sum(path == '/p/2' for _,path in site[2][before:]) == 1
    redirected = next(n for n in store.graph(run_id)['nodes'] if n['url'].endswith('/redirect'))
    assert redirected['status'] == 'duplicate'


async def test_limits_timeout(crawl, store, site):
    run_id = await crawl(page_limit=2,resource_limit=0,links="all")
    assert store.metrics(run_id)["pages"] == 2
    assert store.metrics(run_id)["resources"] == 0
    assert 'limity' in store.get_run(run_id)["message"]
    slow = await crawl(url=site[0]+"/slow", timeout=.1)
    assert store.metrics(slow)["failures"] == 1


async def test_csv_sqlite_and_missing_keywords(crawl, store):
    run_id = await crawl(strategy="bfs")
    raw = csv_export(store,run_id)
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    assert rows[0] == ['URL','Keyword']
    assert rows[1][1] == 'sieć, "Łódź"'
    assert any(row[1] == '' for row in rows[2:])
    assert list(csv.reader(io.StringIO(csv_export(store,run_id,['Title','Body']).decode('utf-8-sig'))))[0] == ['Title','Body']
    db = sqlite3.connect(':memory:')
    db.deserialize(sqlite_export(store,run_id))
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert db.execute('SELECT COUNT(*) FROM metadata').fetchone()[0] == len(rows)-1
    assert db.execute('SELECT COUNT(*) FROM links').fetchone()[0] > 20
    assert db.execute('SELECT config FROM run').fetchone()[0]
    db.close()


async def test_cancel_queue_and_restart(store, site):
    cfg = Config(url=site[0]+'/',delay=.1)
    ids = [store.create_run('session',cfg) for _ in range(2)]
    engine=Engine(store)
    engine.start(ids)
    await asyncio.sleep(.25)
    assert engine.busy
    with pytest.raises(RuntimeError):
        engine.start(ids)
    engine.cancelled.set()
    await engine.task
    assert all(store.get_run(r)['status']=='cancelled' for r in ids)
    assert store.records(ids[0])
    leftover=store.create_run('session',cfg)
    reopened=Store(store.path)
    assert reopened.get_run(leftover)['status']=='interrupted'
    assert reopened.records(ids[0])


async def test_datasets_report_and_experiments(store, site):
    assert 'Brak zakończonego badania' in report(store,'session')
    engine=Engine(store)
    for purpose, scope, depth in [('dataset_A','web',2),('dataset_B','server',3)]:
        run=store.create_run('session',Config(url=site[0]+'/',delay=0,scope=scope,depth=depth,strategy='bfs'),purpose)
        await engine.crawl(run)
    ds=datasets(store,'session')
    assert ds['A']['fields']==['URL','Keyword']
    assert ds['A']['size']==len(csv_export(store,ds['A']['run_id']))
    assert ds['comparison']['common'] >= 20 and ds['comparison']['only_a'] >= 1 and ds['comparison']['only_b'] >= 1
    for strategy in ('dfs','bfs'):
        r=store.create_run('session',Config(url=site[0]+'/',delay=0,strategy=strategy),'experiment','batch')
        await engine.crawl(r)
    comparison=experiments(store,'session')
    assert 'Najwydajniejszy' in comparison['recommendation']
    assert comparison['findings'][0]['comparisons']
    result=report(store,'session')
    assert all(f'<h2>{i}.' in result for i in range(1,9))
    assert '<svg' in result and 'Łódź' in result


async def test_normalization_and_extraction():
    assert normalize('HTTPS://Example.com:443/a#b')=='https://example.com/a'
    assert normalize('mailto:x@y') is None
    assert normalize('https://user:password@example.com') is None
    assert normalize('../a#b','https://example.com/x/y')=='https://example.com/a'
    metadata,links=extract('<base href="/new/"><a href="x">x</a><img src="p.png"><script>secret</script><body>Visible</body>','https://example.com/','images')
    assert links==[('https://example.com/new/x','hyperlink'),('https://example.com/new/p.png','image')]
    assert 'secret' not in metadata['body']
    assert normalize('http://[invalid') is None
    _, found = extract('<a href="http://[invalid">bad</a>', 'https://example.com/', 'all')
    assert found[0][0] == 'http://[invalid'


async def test_dfs_reexpands_shorter_path_without_refetch(crawl, store, site):
    before = len(site[2])
    run_id = await crawl(url=site[0]+'/shorter',strategy='dfs',depth=3)
    nodes = store.graph(run_id)['nodes']
    shared = next(n for n in nodes if n['url'].endswith('/shared'))
    child = next(n for n in nodes if n['url'].endswith('/child'))
    assert shared['depth'] == 3 and shared['distance'] == 2
    assert child['status'] == 'ok' and child['distance'] == 3
    assert sum(path == '/shared' for _,path in site[2][before:]) == 1
