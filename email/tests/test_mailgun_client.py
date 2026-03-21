#!/usr/bin/env python3
"""Testes unitários — cliente Mailgun (stdlib)."""

from __future__ import annotations

import unittest

from lib.mailgun_client import (
    MailgunConfigError,
    build_mailgun_messages_url,
    mailgun_base_url,
    mask_secret,
    validate_mailgun_inputs,
    validate_mailgun_send_fields,
)


class TestMailgunBaseUrl(unittest.TestCase):
    def test_us(self) -> None:
        self.assertEqual(mailgun_base_url("us"), "https://api.mailgun.net")

    def test_eu(self) -> None:
        self.assertEqual(mailgun_base_url("eu"), "https://api.eu.mailgun.net")

    def test_region_case_insensitive(self) -> None:
        self.assertEqual(mailgun_base_url("EU"), "https://api.eu.mailgun.net")

    def test_invalid_region(self) -> None:
        with self.assertRaises(MailgunConfigError):
            mailgun_base_url("ap")


class TestBuildMessagesUrl(unittest.TestCase):
    def test_build(self) -> None:
        u = build_mailgun_messages_url(
            base_url="https://api.mailgun.net",
            domain="mg.example.com",
        )
        self.assertEqual(u, "https://api.mailgun.net/v3/mg.example.com/messages")


class TestMaskSecret(unittest.TestCase):
    def test_none(self) -> None:
        self.assertIn("não definido", mask_secret(None))

    def test_short(self) -> None:
        self.assertEqual(mask_secret("ab"), "***")

    def test_long(self) -> None:
        m = mask_secret("key-abcdefghijklmnopqrstuvwxyz")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", m)
        self.assertTrue(m.startswith("key"))


class TestValidate(unittest.TestCase):
    def test_send_fields_ok(self) -> None:
        r = validate_mailgun_send_fields(
            domain="mg.example.com",
            region="us",
            from_addr="hi@example.com",
            api_key="secret",
        )
        self.assertEqual(r["domain"], "mg.example.com")

    def test_empty_domain(self) -> None:
        with self.assertRaises(MailgunConfigError):
            validate_mailgun_send_fields(
                domain="",
                region="us",
                from_addr="a@b.co",
                api_key="k",
            )

    def test_full_inputs_admin(self) -> None:
        r = validate_mailgun_inputs(
            domain="example.com",
            region="eu",
            from_addr="from@example.com",
            admin_email="admin@example.com",
            api_key="x",
        )
        self.assertEqual(r["admin_email"], "admin@example.com")


if __name__ == "__main__":
    unittest.main()
