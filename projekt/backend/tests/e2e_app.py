"""Playwright-only application: real HTTP fixture, no production safety bypass."""

import atexit

from lab_site import LAB_GRAPH
from site_fixture import GRAPH, website

from app.main import create_app

fixture = website({**GRAPH, **LAB_GRAPH, "/slow": '<a href="/later">Later</a>', "/later": "later"})
site = fixture.__enter__()
atexit.register(fixture.__exit__, None, None, None)
app = create_app(transport_factory=site.transport)
