"""
Testes unitários para patches/patch_irc.py (parsing, idempotência, autoconnect).
Executar na raiz do repo: python3 -m unittest tests.test_patch_irc -v

No Windows o módulo alvo não carrega (falta ``pwd``); os testes são ignorados.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_patch_irc():
    path = ROOT / "patches" / "patch_irc.py"
    spec = importlib.util.spec_from_file_location("patch_irc_test_mod", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _PatchIrcTestBase(unittest.TestCase):
    p = None

    @classmethod
    def setUpClass(cls) -> None:
        if sys.platform.startswith("win"):
            raise unittest.SkipTest("patch_irc e estes testes requerem Unix (pwd)")
        cls.p = _load_patch_irc()


def _runv_section(p, username: str) -> str:
    nicks = p.expected_nicks(username)
    return f"""[server]
runv.addresses = "irc.portalidea.com.br/6697"
runv.tls = on
runv.nicks = "{nicks}"
runv.username = "{username}"
runv.realname = "{username}"
runv.autoconnect = on
runv.autojoin = "#runv"
"""


class TestParseServers(_PatchIrcTestBase):
    def test_parse_all_server_names(self) -> None:
        p = self.p
        text = """
[server]
runv.addresses = "x"
libera.addresses = "y"
runv.tls = on
"""
        names = p.parse_all_server_names(text)
        self.assertEqual(names, {"runv", "libera"})

    def test_parse_server_options(self) -> None:
        p = self.p
        text = _runv_section(p, "alice")
        o = p.parse_server_options(text, "runv")
        self.assertEqual(o.get("addresses"), "irc.portalidea.com.br/6697")
        self.assertTrue(p.tls_effective(o))
        self.assertEqual(o.get("autojoin"), "#runv")


class TestCompliance(_PatchIrcTestBase):
    def setUp(self) -> None:
        self.log = logging.getLogger("t")
        self.log.disabled = True

    def test_fully_compliant_noop(self) -> None:
        p = self.p
        body = _runv_section(p, "bob")
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, encoding="utf-8") as f:
            f.write(body)
            path = Path(f.name)
        try:
            self.assertTrue(
                p.config_matches(
                    path,
                    server="runv",
                    host="irc.portalidea.com.br",
                    port=6697,
                    tls=True,
                    unix_username="bob",
                    autojoin="#runv",
                    log=self.log,
                )
            )
        finally:
            path.unlink(missing_ok=True)

    def test_other_autoconnect_breaks_compliance(self) -> None:
        p = self.p
        body = _runv_section(p, "bob") + """
libera.addresses = "irc.libera.chat/6697"
libera.tls = on
libera.autoconnect = on
"""
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, encoding="utf-8") as f:
            f.write(body)
            path = Path(f.name)
        try:
            self.assertFalse(
                p.config_matches(
                    path,
                    server="runv",
                    host="irc.portalidea.com.br",
                    port=6697,
                    tls=True,
                    unix_username="bob",
                    autojoin="#runv",
                    log=self.log,
                )
            )
        finally:
            path.unlink(missing_ok=True)

    def test_disable_other_chain(self) -> None:
        p = self.p
        body = _runv_section(p, "bob") + """
libera.addresses = "irc.libera.chat/6697"
libera.autoconnect = on
"""
        chain = p.build_disable_other_autoconnect_chain(body, "runv")
        self.assertIn("/set irc.server.libera.autoconnect off", chain)

    def test_disable_chain_empty_when_all_off(self) -> None:
        p = self.p
        body = _runv_section(p, "bob") + """
libera.addresses = "irc.libera.chat/6697"
libera.autoconnect = off
"""
        chain = p.build_disable_other_autoconnect_chain(body, "runv")
        self.assertEqual(chain, "")

    def test_server_add_has_tls_not_autoconnect_flag(self) -> None:
        p = self.p
        chain = p.build_apply_command_chain(
            server="runv",
            host="irc.portalidea.com.br",
            port=6697,
            tls=True,
            unix_username="u",
            autojoin="#runv",
        )
        self.assertIn("/server add runv irc.portalidea.com.br/6697 -tls", chain)
        first = chain.split(" ; ")[0]
        self.assertNotIn("-autoconnect", first)


if __name__ == "__main__":
    unittest.main()
