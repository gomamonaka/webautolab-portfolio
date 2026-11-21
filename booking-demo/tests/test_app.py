# -*- coding: utf-8 -*-
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app


class BookingTest(unittest.TestCase):
    def setUp(self):
        self.conn = app.connect(":memory:")
        app.init_db(self.conn)
        app.seed(self.conn)
        self.tomorrow = (date.today() + timedelta(days=1)).isoformat()

    def tearDown(self):
        self.conn.close()

    def test_seed_counts(self):
        menus = self.conn.execute("SELECT COUNT(*) FROM menus").fetchone()[0]
        bookings = self.conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        self.assertEqual(menus, 4)
        self.assertGreaterEqual(bookings, 10)

    def test_create_booking_ok(self):
        bid = app.create_booking(self.conn, 1, self.tomorrow, "17:00", "テスト客", "090-1111-2222")
        row = self.conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
        self.assertEqual(row["status"], "pending")

    def test_double_booking_blocked(self):
        app.create_booking(self.conn, 1, self.tomorrow, "16:00", "一人目", "x")
        with self.assertRaises(ValueError):
            app.create_booking(self.conn, 1, self.tomorrow, "16:00", "二人目", "y")

    def test_cancelled_slot_reusable(self):
        bid = app.create_booking(self.conn, 1, self.tomorrow, "15:00", "取消客", "x")
        app.change_status(self.conn, bid, "cancelled")
        bid2 = app.create_booking(self.conn, 1, self.tomorrow, "15:00", "新規客", "y")
        self.assertNotEqual(bid, bid2)

    def test_available_slots_excludes_taken(self):
        slots = app.available_slots(self.conn, self.tomorrow)
        # サンプルで 10:00 は確定済み予約がある
        self.assertNotIn("10:00", slots)
        self.assertIn("17:00", slots)

    def test_status_flow(self):
        bid = app.create_booking(self.conn, 1, self.tomorrow, "14:00", "遷移客", "x")
        app.change_status(self.conn, bid, "confirmed")
        app.change_status(self.conn, bid, "visited")
        row = self.conn.execute("SELECT status FROM bookings WHERE id=?", (bid,)).fetchone()
        self.assertEqual(row["status"], "visited")

    def test_invalid_transition(self):
        bid = app.create_booking(self.conn, 1, self.tomorrow, "13:00", "不正遷移", "x")
        with self.assertRaises(ValueError):
            app.change_status(self.conn, bid, "visited")  # 仮予約→来店済みは不可
        app.change_status(self.conn, bid, "cancelled")
        with self.assertRaises(ValueError):
            app.change_status(self.conn, bid, "confirmed")  # キャンセル後は不可

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            app.create_booking(self.conn, 1, self.tomorrow, "12:00", "  ", "x")

    def test_reminder_text(self):
        bid = app.create_booking(self.conn, 2, self.tomorrow, "11:00", "文面客", "x")
        row = self.conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
        text = app.reminder_text(row, "カット＋カラー")
        self.assertIn("文面客 様", text)
        self.assertIn(self.tomorrow, text)
        self.assertIn("11:00", text)
        self.assertIn("カット＋カラー", text)


if __name__ == "__main__":
    unittest.main()
