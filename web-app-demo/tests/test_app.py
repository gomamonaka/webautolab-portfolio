"""備品貸出管理アプリの単体テスト（標準unittestのみ）。

実行方法:
    python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app


def d(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


class LoanLogicTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = app.get_conn(self.db_path)
        app.init_db(self.conn)
        self.item_id = app.add_item(self.conn, "ノートPC", "PC・周辺機器", 2, "")

    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)

    def test_checkout_records_loan_and_reduces_availability(self):
        app.checkout(self.conn, self.item_id, "山田 花子", d(7))
        item = self.conn.execute(
            "SELECT * FROM items WHERE id = ?", (self.item_id,)
        ).fetchone()
        self.assertEqual(app.available_qty(self.conn, item), 1)
        loans = app.list_loans(self.conn, active_only=True)
        self.assertEqual(len(loans), 1)
        self.assertEqual(loans[0]["borrower"], "山田 花子")

    def test_checkout_fails_when_no_stock(self):
        app.checkout(self.conn, self.item_id, "佐藤 健", d(7))
        app.checkout(self.conn, self.item_id, "鈴木 美咲", d(7))
        with self.assertRaises(ValueError):
            app.checkout(self.conn, self.item_id, "高橋 翔", d(7))

    def test_checkout_fails_for_unknown_item(self):
        with self.assertRaises(ValueError):
            app.checkout(self.conn, 9999, "山田 花子", d(7))

    def test_checkout_fails_without_borrower(self):
        with self.assertRaises(ValueError):
            app.checkout(self.conn, self.item_id, "  ", d(7))

    def test_return_restores_availability(self):
        loan_id = app.checkout(self.conn, self.item_id, "山田 花子", d(7))
        app.return_loan(self.conn, loan_id)
        item = self.conn.execute(
            "SELECT * FROM items WHERE id = ?", (self.item_id,)
        ).fetchone()
        self.assertEqual(app.available_qty(self.conn, item), 2)
        self.assertEqual(app.list_loans(self.conn, active_only=True), [])

    def test_overdue_when_past_due_and_not_returned(self):
        app.checkout(self.conn, self.item_id, "山田 花子", d(-1), loan_date=d(-8))
        loan = app.list_loans(self.conn, active_only=True)[0]
        self.assertTrue(loan["overdue"])
        self.assertTrue(app.is_overdue(loan))

    def test_not_overdue_when_due_in_future(self):
        app.checkout(self.conn, self.item_id, "山田 花子", d(3))
        loan = app.list_loans(self.conn, active_only=True)[0]
        self.assertFalse(loan["overdue"])

    def test_not_overdue_after_return_even_if_late(self):
        loan_id = app.checkout(
            self.conn, self.item_id, "山田 花子", d(-5), loan_date=d(-12)
        )
        app.return_loan(self.conn, loan_id)
        loan = app.list_loans(self.conn)[0]
        self.assertFalse(loan["overdue"])
        self.assertFalse(app.is_overdue(loan))

    def test_delete_blocked_while_on_loan(self):
        app.checkout(self.conn, self.item_id, "山田 花子", d(7))
        self.assertFalse(app.delete_item(self.conn, self.item_id))
        self.assertIsNotNone(
            self.conn.execute(
                "SELECT * FROM items WHERE id = ?", (self.item_id,)
            ).fetchone()
        )

    def test_delete_allowed_when_not_on_loan(self):
        self.assertTrue(app.delete_item(self.conn, self.item_id))
        self.assertIsNone(
            self.conn.execute(
                "SELECT * FROM items WHERE id = ?", (self.item_id,)
            ).fetchone()
        )

    def test_search_filters_by_keyword(self):
        app.add_item(self.conn, "プロジェクター", "会議機材", 1, "")
        hits = app.search_items(self.conn, "プロジェクター")
        self.assertEqual([h["name"] for h in hits], ["プロジェクター"])
        self.assertEqual(len(app.search_items(self.conn, "")), 2)
        self.assertEqual(app.search_items(self.conn, "存在しない備品"), [])

    def test_csv_export_includes_status(self):
        app.checkout(self.conn, self.item_id, "山田 花子", d(-1), loan_date=d(-8))
        csv_text = app.loans_to_csv(self.conn)
        self.assertIn("備品名,借りた人,貸出日,返却期限,返却日,状態", csv_text)
        self.assertIn("山田 花子", csv_text)
        self.assertIn("期限切れ", csv_text)


class SeedTest(unittest.TestCase):
    def test_seed_inserts_sample_data_once(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = app.get_conn(db_path)
            app.init_db(conn)
            app.seed_sample_data(conn)
            app.seed_sample_data(conn)  # 2回呼んでも増えない
            items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            loans = conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
            self.assertEqual(items, 10)
            self.assertEqual(loans, 10)
            overdue = [l for l in app.list_loans(conn, active_only=True) if l["overdue"]]
            self.assertGreaterEqual(len(overdue), 1)
            conn.close()
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
