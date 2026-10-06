"""Preview the static report at its production URL path; no model calls."""
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import argparse

ROOT=Path(__file__).resolve().parents[1]/'site'
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def translate_path(self,path):
        route=urlsplit(path).path
        if route in {'/','/strataflash','/strataflash/'}: route='/index.html'
        elif route.startswith('/strataflash/'): route=route[len('/strataflash'):]
        else: route='/__unavailable__'
        return super().translate_path(route)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8000);args=parser.parse_args()
    print(f'Preview: http://127.0.0.1:{args.port}/strataflash/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
