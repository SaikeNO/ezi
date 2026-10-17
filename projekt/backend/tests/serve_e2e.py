import tempfile
from pathlib import Path
import uvicorn
from backend.app import create_app
from .fixture_site import sites

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='ezi-e2e-') as directory, sites(8767,8768):
        uvicorn.run(create_app(Path(directory)/'test.sqlite'),host='127.0.0.1',port=8766,log_level='warning')
