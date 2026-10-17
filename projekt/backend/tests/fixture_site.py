"""Test-only sites; never mounted by the application."""
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@contextmanager
def sites(port=0, external_port=0):
    hits = []
    external_url = ""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            hits.append((self.server.server_port, self.path))
            code, content_type = 200, "text/html; charset=utf-8"
            if self.path == "/robots.txt":
                content_type = "text/plain"
                body = "User-agent: *\nDisallow: /blocked\n"
            elif self.path == "/":
                body = '<title>Łódź — test</title><meta name="description" content="Opis strony"><meta name="keywords" content="sieć, &quot;Łódź&quot;">'
                body += ''.join(f'<a href="/p/{i}">Strona {i}</a>' for i in range(1, 22))
                body += f'<a href="/p/1#dup">Duplikat</a><a href="{external_url}/external">Zewnętrzna</a>'
                body += '<img src="/image.png"><link rel="stylesheet" href="/style.css"><script src="/script.js">bad hidden</script>'
                body += '<a href="/blocked">Zakaz</a><a href="mailto:test@example.com">Mail</a><a href="/redirect">Redirect</a><a href="/broken">404</a>'
            elif self.path == "/p/1":
                body = '<title>Poziom 1</title><a href="/level2">Dalej</a><a href="/">Cykl</a>'
            elif self.path.startswith("/p/"):
                body = '<title>Podstrona</title><body>Polska treść bez słów kluczowych</body>'
            elif self.path == "/level2":
                body = '<title>Poziom 2</title><a href="/level3">Dalej</a>'
            elif self.path == "/level3":
                body = '<title>Poziom 3</title><a href="/level4">Głębiej</a>'
            elif self.path in ("/level4", "/external", "/blocked"):
                body = '<title>Strona końcowa</title>'
            elif self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/p/2")
                self.end_headers()
                return
            elif self.path == "/redirect-external":
                self.send_response(302)
                self.send_header("Location", external_url + "/external")
                self.end_headers()
                return
            elif self.path == "/redirect-blocked":
                self.send_response(302)
                self.send_header("Location", "/blocked")
                self.end_headers()
                return
            elif self.path == "/slow":
                time.sleep(.4)
                body = 'slow'
            elif self.path == "/image.png":
                body, content_type = 'binary image', 'image/png'
            elif self.path == "/style.css":
                body, content_type = 'body {}', 'text/css'
            elif self.path == "/script.js":
                body, content_type = 'console.log(1)', 'text/javascript'
            elif self.path == "/order":
                body = '<a href="/a">a</a><a href="/b">b</a>'
            elif self.path == "/shorter":
                body = '<a href="/deep1">deep</a><a href="/shallow">shallow</a>'
            elif self.path == "/deep1":
                body = '<a href="/deep2">deep</a>'
            elif self.path == "/deep2":
                body = '<a href="/shared">shared</a>'
            elif self.path == "/shallow":
                body = '<a href="/shared">shared</a>'
            elif self.path == "/shared":
                body = '<a href="/child">child</a>'
            elif self.path == "/child":
                body = '<title>Reachable at depth 3</title>'
            elif self.path == "/a":
                body = '<a href="/aa">aa</a>'
            elif self.path in ("/aa", "/b"):
                body = '<title>Order</title>'
            else:
                body, code = 'Not found', 404
            encoded = body.encode('utf-8')
            try:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    servers = [ThreadingHTTPServer(("127.0.0.1", p), Handler) for p in (port, external_port)]
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    external_url = f"http://127.0.0.1:{servers[1].server_port}"
    for thread in threads:
        thread.start()
    try:
        yield f"http://127.0.0.1:{servers[0].server_port}", external_url, hits
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()


if __name__ == "__main__":
    with sites() as (url, _, __):
        print(url, flush=True)
        threading.Event().wait()
