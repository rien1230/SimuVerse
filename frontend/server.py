"""Minimal local HTTP server wrapper for frontend development."""

import os, sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

os.chdir("/Users/rien/Documents/cat1 copy 7/frontend")
HTTPServer(("127.0.0.1", 3000), SimpleHTTPRequestHandler).serve_forever()
