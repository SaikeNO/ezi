import time
from fastapi.testclient import TestClient
from backend.app import create_app


def test_api_full_flow(tmp_path,site):
    with TestClient(create_app(tmp_path/'api.sqlite')) as client:
        assert client.post('/api/sessions',json={'config':{'url':'file:///test'}}).status_code==422
        config={'url':site[0]+'/', 'delay':0, 'strategy':'bfs','page_limit':30}
        session=client.post('/api/sessions',json={'name':'<script>Łódź</script>','config':config}).json()
        sid=session['id']
        assert client.get(f'/api/sessions/{sid}').json()['url']==config['url']
        assert client.get('/api/sessions/missing').status_code==404
        assert client.get('/api/runs/missing').status_code==404
        assert client.post(f'/api/sessions/{sid}/runs',json={**config,'url':site[1]}).status_code==422
        run_id=client.post(f'/api/sessions/{sid}/runs',json=config).json()['run_ids'][0]
        deadline=time.monotonic()+20
        while client.get('/api/status').json()['busy'] and time.monotonic()<deadline:
            time.sleep(.02)
        assert client.get(f'/api/runs/{run_id}').json()['metrics']['qualifies']
        assert client.get(f'/api/runs/{run_id}/graph').json()['nodes']
        assert client.get(f'/api/runs/{run_id}/records').json()
        assert client.get(f'/api/runs/{run_id}/export.csv').content.decode('utf-8-sig').startswith('URL,Keyword\r\n')
        assert client.get(f'/api/runs/{run_id}/export.csv?fields=Wrong').status_code==422
        assert client.get(f'/api/runs/{run_id}/export.sqlite').content.startswith(b'SQLite format 3')
        report=client.get(f'/api/sessions/{sid}/report?download=true')
        assert 'attachment' in report.headers['content-disposition']
        assert '&lt;script&gt;Łódź&lt;/script&gt;' in report.text
        assert '<script>Łódź</script>' not in report.text
        batch=client.post(f'/api/sessions/{sid}/experiments',json={**config,'depth':0,'delay':.1}).json()
        assert len(batch['run_ids'])==12
        assert client.post(f'/api/sessions/{sid}/runs',json=config).status_code==409
        client.post('/api/cancel')
        while client.get('/api/status').json()['busy'] and time.monotonic()<deadline:
            time.sleep(.02)
        assert len(client.get(f'/api/sessions/{sid}/comparison').json()['runs'])==13
