"""Tiny helper to serve the frontend from this folder during local testing."""

import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0]]
from http.server import HTTPServer, SimpleHTTPRequestHandler
HTTPServer(("", 5001), SimpleHTTPRequestHandler).serve_forever()
