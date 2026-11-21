# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app


class TestClassify(unittest.TestCase):
    def test_hours(self):
        self.assertEqual(app.classify("営業時間を教えてください"), "営業時間")
        self.assertEqual(app.classify("定休日はいつですか"), "営業時間")

    def test_price(self):
        self.assertEqual(app.classify("カットの料金はいくらですか"), "料金")

    def test_booking(self):
        self.assertEqual(app.classify("予約したいのですが空いていますか"), "予約")

    def test_access(self):
        self.assertEqual(app.classify("お店の場所と行き方を教えてください"), "アクセス")

    def test_other(self):
        self.assertEqual(app.classify("ありがとうございました"), "その他")


class TestDraft(unittest.TestCase):
    def test_draft_contains_shop_and_hours(self):
        category, text = app.make_draft("営業時間は？")
        self.assertEqual(category, "営業時間")
        self.assertIn(app.SHOP_NAME, text)
        self.assertIn("10:00", text)

    def test_fallback_draft(self):
        category, text = app.make_draft("はじめまして")
        self.assertEqual(category, "その他")
        self.assertTrue(len(text) > 0)


class TestFlow(unittest.TestCase):
    def setUp(self):
        self.demo = app.Demo()

    def test_send_creates_pending_draft(self):
        draft = self.demo.customer_send("料金を教えてください")
        self.assertEqual(draft["status"], "下書き（未送信）")
        self.assertEqual(draft["category"], "料金")
        state = self.demo.state()
        self.assertEqual(len(state["customer_messages"]), 1)
        self.assertEqual(len(state["log"]), 1)

    def test_empty_message_rejected(self):
        with self.assertRaises(ValueError):
            self.demo.customer_send("  ")

    def test_approve_delivers_to_customer(self):
        draft = self.demo.customer_send("予約したいです")
        self.demo.approve(draft["id"])
        state = self.demo.state()
        self.assertEqual(state["drafts"][0]["status"], "送信済み")
        self.assertEqual(state["customer_messages"][-1]["from"], "shop")

    def test_approve_with_edited_text(self):
        draft = self.demo.customer_send("営業時間は？")
        self.demo.approve(draft["id"], text="編集した返信です")
        state = self.demo.state()
        self.assertEqual(state["customer_messages"][-1]["text"], "編集した返信です")

    def test_double_approve_rejected(self):
        draft = self.demo.customer_send("予約したいです")
        self.demo.approve(draft["id"])
        with self.assertRaises(ValueError):
            self.demo.approve(draft["id"])

    def test_approve_unknown_id(self):
        with self.assertRaises(KeyError):
            self.demo.approve(9999)


if __name__ == "__main__":
    unittest.main()
