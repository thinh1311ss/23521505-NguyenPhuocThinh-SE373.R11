# -*- coding: utf-8 -*-
"""Unit tests kiểm thử độc lập 4 lớp harness của Agent Đặt Vé Máy Bay.

Chạy:
    python3 test_harness.py
"""
import unittest
from lib.mock_flight_db import mock_db
from lib.harness import (
    BookingConstraints,
    ConstraintValidator,
    GroundingVerifier,
    CompletionVerifier,
    PermissionGuard,
    PermissionStatus,
    LoopDetector,
    StallDetector,
    HandoffManager,
)


class TestFlightHarnessLayers(unittest.TestCase):

    def setUp(self):
        mock_db.reset()
        self.constraints = BookingConstraints(
            origin="SGN",
            destination="DAD",
            depart_date="2026-10-15",
            time_window="sang",
            max_price=2000000,
            passenger_name="Nguyen Van A",
            passenger_id="079201009999",
        )

    # =========================================================================
    # LỚP 1 · RÀNG BUỘC LÀ DỮ LIỆU & KIỂM TRA CĂN CỨ (GROUNDING)
    # =========================================================================
    def test_constraint_validator(self):
        # Chuyến bay hợp lệ (VJ624: SGN->DAD, 06:30 sáng, 1.420.000đ <= 2tr)
        f_valid = {
            "origin": "SGN",
            "destination": "DAD",
            "depart_date": "2026-10-15",
            "depart_time": "06:30",
            "price": 1420000,
        }
        valid, violations = ConstraintValidator.validate_flight(f_valid, self.constraints)
        self.assertTrue(valid)
        self.assertEqual(len(violations), 0)

        # Chuyến bay sai giờ (14:20 chiều trong khi cần bay sáng)
        f_wrong_time = dict(f_valid, depart_time="14:20")
        valid, violations = ConstraintValidator.validate_flight(f_wrong_time, self.constraints)
        self.assertFalse(valid)
        self.assertTrue(any("buổi" in v for v in violations))

        # Chuyến bay vượt trần ngân sách (2.150.000đ > 2.000.000đ)
        f_expensive = dict(f_valid, price=2150000)
        valid, violations = ConstraintValidator.validate_flight(f_expensive, self.constraints)
        self.assertFalse(valid)
        self.assertTrue(any("Vượt trần giá" in v for v in violations))

    def test_grounding_verifier(self):
        tool_observations = [
            '{"flight_code":"VJ624","price":1420000,"depart_time":"06:30"}',
            '{"booking_code":"BK-VJ624-1001","payment_id":"PAY-1001-OK"}',
        ]
        # Câu trả lời trung thực, số liệu có căn cứ
        honest_answer = (
            "Chuyến bay VJ624 lúc 06:30 có giá 1.420.000đ. "
            "Đã giữ chỗ BK-VJ624-1001 và thanh toán PAY-1001-OK."
        )
        res_honest = GroundingVerifier.check_grounding(honest_answer, tool_observations)
        self.assertTrue(res_honest["passed"])
        self.assertEqual(len(res_honest["ungrounded_facts"]), 0)

        # Câu trả lời bịa đặt (Hallucination: chuyến bay ảo AA999 giá 500.000đ)
        hallucinated_answer = (
            "Tôi tìm thấy chuyến bay AA999 giá 500.000đ lúc 05:00 ngày 2026-10-15."
        )
        res_hallucinated = GroundingVerifier.check_grounding(hallucinated_answer, tool_observations)
        self.assertFalse(res_hallucinated["passed"])
        self.assertIn("AA999", res_hallucinated["ungrounded_facts"])
        self.assertIn("500.000đ", res_hallucinated["ungrounded_facts"])

    # =========================================================================
    # LỚP 2 · TIÊU CHÍ HOÀN THÀNH KIỂM BẰNG CODE (COMPLETION VERIFIER)
    # =========================================================================
    def test_completion_verifier(self):
        # 1. Booking chưa thanh toán (chỉ mới pending) -> Chưa hoàn thành
        b_pending = mock_db.create_booking(
            flight_code="VJ624",
            passenger_name="Nguyen Van A",
            passenger_id="079201009999",
        )
        code = b_pending["booking_code"]
        res_pending = CompletionVerifier.verify_booking(code, self.constraints)
        self.assertFalse(res_pending["is_completed"])
        self.assertIn("status_confirmed", res_pending["failed_reasons"])
        self.assertIn("is_paid", res_pending["failed_reasons"])

        # 2. Đã thanh toán xác nhận -> Đạt tiêu chí hoàn thành
        mock_db.pay_booking(code)
        res_confirmed = CompletionVerifier.verify_booking(code, self.constraints)
        self.assertTrue(res_confirmed["is_completed"])
        self.assertEqual(len(res_confirmed["failed_reasons"]), 0)

        # 3. Chuyến bay có giá vượt trần (VN136: 2.150.000đ) -> Code phát hiện vi phạm
        b_expensive = mock_db.create_booking(
            flight_code="VN136",
            passenger_name="Nguyen Van A",
            passenger_id="079201009999",
        )
        mock_db.pay_booking(b_expensive["booking_code"])
        res_exp = CompletionVerifier.verify_booking(b_expensive["booking_code"], self.constraints)
        self.assertFalse(res_exp["is_completed"])
        self.assertIn("price_within_budget", res_exp["failed_reasons"])

    # =========================================================================
    # LỚP 3 · KIỂM QUYỀN VÀ PHÊ DUYỆT (PERMISSION GUARD)
    # =========================================================================
    def test_permission_guard(self):
        guard = PermissionGuard(autopay_limit=1500000)

        # 1. Tra cứu -> Tự động cho phép
        p_search = guard.check_permission("search_flights", {"origin": "SGN", "destination": "DAD"})
        self.assertEqual(p_search["status"], PermissionStatus.ALLOWED)

        # 2. Đặt vé không hoàn hủy (VN122) hoặc giá > 1.5tr (1.850.000đ) -> Bắt buộc xin phép
        p_book = guard.check_permission("book_seat", {"flight_code": "VN122"})
        self.assertEqual(p_book["status"], PermissionStatus.REQUIRES_APPROVAL)
        self.assertIn("why", p_book)

        # 3. Phê duyệt hành động
        guard.grant_approval(p_book["action_sig"])
        p_approved = guard.check_permission("book_seat", {"flight_code": "VN122"})
        self.assertEqual(p_approved["status"], PermissionStatus.ALLOWED)

        # 4. Thanh toán trừ tiền -> Luôn yêu cầu phê duyệt
        p_pay = guard.check_permission("pay_ticket", {"booking_code": "BK-VN122-1001"})
        self.assertEqual(p_pay["status"], PermissionStatus.REQUIRES_APPROVAL)

    # =========================================================================
    # LỚP 4 · PHÁT HIỆN LẶP / BẾ TẮC VÀ BÀN GIAO (HANDOFF PROTOCOL)
    # =========================================================================
    def test_loop_and_stall_detector(self):
        # Kiểm tra phát hiện lặp
        ld = LoopDetector(window=4, repeat_k=2)
        warn1 = ld.check("check_seat_and_fare", {"flight_code": "VN122"})
        self.assertIsNone(warn1)

        # Lần 2 với cùng tham số -> Báo động LOOP
        warn2 = ld.check("check_seat_and_fare", {"flight_code": "VN122"})
        self.assertIsNotNone(warn2)
        self.assertTrue(warn2.startswith("LOOP"))

        # Kiểm tra phát hiện bế tắc (Stall: tiến triển = 0 qua 2 lần lặp liên tiếp)
        sd = StallDetector(stall_n=2)
        self.assertIsNone(sd.check(progress=0))
        self.assertIsNone(sd.check(progress=0))
        stall_warn = sd.check(progress=0)
        self.assertIsNotNone(stall_warn)
        self.assertTrue(stall_warn.startswith("STALL"))

    def test_handoff_manager(self):
        report = HandoffManager.create_handoff_report(
            stop_reason="LOOP · Đã lặp gọi tool check_seat_and_fare",
            history_actions=["search_flights(...)", "check_seat_and_fare(...)"],
            state_summary={"retries": 2},
            question_for_human="Dịch vụ vé phản hồi lỗi lặp lại. Có muốn thử chuyến bay khác?",
        )
        # Bàn giao phải có đủ 4 trường thông tin
        self.assertIn("stop_reason", report)
        self.assertIn("da_thu", report)
        self.assertIn("trang_thai", report)
        self.assertIn("cau_hoi_cho_nguoi", report)

        display_text = HandoffManager.format_handoff_display(report)
        self.assertIn("BÁO CÁO BÀN GIAO", display_text)
        self.assertIn("CÂU HỎI CHO NGƯỜI", display_text)


if __name__ == "__main__":
    unittest.main()
