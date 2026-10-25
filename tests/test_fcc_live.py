"""Opt-in real FCC check. Never runs as an accidental part of offline tests."""

import asyncio
import os
import unittest
from dataclasses import replace

from cairo.config import Settings
from cairo.models.service import AIService


@unittest.skipUnless(
    os.getenv("CAIRO_TEST_FCC") == "1", "Set CAIRO_TEST_FCC=1 to contact the local FCC"
)
class FCCLiveTests(unittest.TestCase):
    def test_configured_gateway_model(self):
        conf = Settings.from_env()
        if conf.provider != "fcc":
            self.fail("Set CAIRO_PROVIDER=fcc before the live test")
        # This test follows FCC's current default regardless of a Cairo override.
        ai = AIService(replace(conf, model=""))
        health = ai.health()
        if health["online"] is False:
            self.skipTest("FCC offline")
        self.assertTrue(health["ready"], health.get("error"))
        reply = asyncio.run(
            ai.chat([{"role": "user", "content": "Responda somente: CAIRO OK"}])
        )
        self.assertEqual(reply.content.strip(), "CAIRO OK")
        self.assertEqual(reply.calls, [])
