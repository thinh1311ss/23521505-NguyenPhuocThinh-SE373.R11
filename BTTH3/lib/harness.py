# -*- coding: utf-8 -*-
"""Cài đặt 4 Lớp Harness cho Agent Đặt Vé Máy Bay (SE373 · Buổi 03).

Harness là phần bọc ngoài độc lập với model, hoàn toàn chạy bằng code xác định
(sensor computational, slide 36):
1. Ràng buộc là dữ liệu (Data Constraints & Requirement State & Anti-Hallucination Grounding)
2. Tiêu chí hoàn thành kiểm bằng code (Deterministic Completion Verifier)
3. Kiểm quyền / Phê duyệt (Permission Guard & Human-in-the-Loop)
4. Bàn giao & Phát hiện dừng bất thường (Handoff Manager, LoopDetector, StallDetector)
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from lib.mock_flight_db import mock_db


# =========================================================================
# LỚP 1 · RÀNG BUỘC LÀ DỮ LIỆU & KIỂM TRA CĂN CỨ (GROUNDING)
# =========================================================================
@dataclass
class BookingConstraints:
    """Cấu trúc dữ liệu cố định giữ yêu cầu bài toán (Slide 62).

    Ngăn ngừa hiện tượng 'quên yêu cầu ban đầu' (goal drift) khi nhật ký hội thoại dài ra.
    """
    origin: str                             # SGN, HAN, DAD...
    destination: str                        # DAD, SGN...
    depart_date: str                        # YYYY-MM-DD
    time_window: str = "sang"               # 'sang' (<12:00), 'chieu' (12:00-17:59), 'toi' (>=18:00)
    max_price: int = 2000000                # Trần ngân sách vé (VNĐ)
    passenger_name: str = "Nguyen Van A"
    passenger_id: str = "079201009999"
    seat_class: str = "economy"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "depart_date": self.depart_date,
            "time_window": self.time_window,
            "max_price": self.max_price,
            "passenger_name": self.passenger_name,
            "passenger_id": self.passenger_id,
        }


class ConstraintValidator:
    """Xác thực chuyến bay dựa trên ràng buộc dữ liệu xác định."""

    @staticmethod
    def is_time_in_window(depart_time: str, window: str) -> bool:
        """Kiểm tra giờ bay có khớp với buổi (sáng/chiều/tối) hay không."""
        try:
            hour = int(depart_time.split(":")[0])
            w = window.lower()
            if w == "sang":
                return 5 <= hour < 12
            elif w == "chieu":
                return 12 <= hour < 18
            elif w == "toi":
                return 18 <= hour <= 23 or 0 <= hour < 5
            return True
        except Exception:
            return False

    @classmethod
    def validate_flight(
        cls, flight: dict, constraints: BookingConstraints
    ) -> Tuple[bool, List[str]]:
        """Kiểm tra chuyến bay có thỏa mãn toàn bộ ràng buộc không."""
        violations = []
        if flight.get("origin") != constraints.origin:
            violations.append(f"Sai nơi đi: {flight.get('origin')} != {constraints.origin}")
        if flight.get("destination") != constraints.destination:
            violations.append(f"Sai nơi đến: {flight.get('destination')} != {constraints.destination}")
        if flight.get("depart_date") != constraints.depart_date:
            violations.append(f"Sai ngày: {flight.get('depart_date')} != {constraints.depart_date}")
        if not cls.is_time_in_window(flight.get("depart_time", ""), constraints.time_window):
            violations.append(f"Sai buổi bay: {flight.get('depart_time')} không thuộc buổi '{constraints.time_window}'")
        if flight.get("price", 0) > constraints.max_price:
            violations.append(
                f"Vượt trần giá: {flight.get('price'):,}đ > {constraints.max_price:,}đ"
            )
        return len(violations) == 0, violations


# Các mẫu regex trích xuất thực thể quan trọng để chống ảo giác (Grounding / Anti-Hallucination)
MAU_DU_KIEN_VE = [
    r"\b[A-Z]{2}\d{3,4}\b",                           # Mã chuyến bay: VN122, VJ624, QH150
    r"\bBK-[A-Z0-9]+-\d+\b",                          # Mã đặt vé: BK-VJ624-1001
    r"\bPAY-\d+-OK\b",                                # Mã thanh toán: PAY-1001-OK
    r"\d{1,3}(?:\.\d{3})+(?:đ|\s?VNĐ|\s?đồng)?",      # Số tiền: 1.420.000đ, 2.000.000 VNĐ
    r"\d{1,2}:\d{2}",                                 # Giờ: 08:15, 14:20
    r"\d{4}-\d{2}-\d{2}",                             # Ngày: 2026-10-15
]


class GroundingVerifier:
    """Đối chiếu câu trả lời và tham số tool với kết quả observation đã nhận (Slide 58-59)."""

    @staticmethod
    def extract_facts(text: str) -> List[str]:
        facts = []
        for pat in MAU_DU_KIEN_VE:
            facts += re.findall(pat, text)
        return list(dict.fromkeys(facts))

    @classmethod
    def check_grounding(
        cls,
        candidate_text: str,
        tool_observations: List[str],
        allowed_context: Optional[str] = None,
    ) -> dict:
        corpus = " ".join(str(obs) for obs in tool_observations)
        if allowed_context:
            corpus += " " + str(allowed_context)

        facts = cls.extract_facts(candidate_text)
        details = []
        for f in facts:
            grounded = f in corpus
            if not grounded:
                digits_only = re.sub(r"[^\d]", "", f)
                if len(digits_only) >= 4 and digits_only in corpus:
                    grounded = True
            details.append({"fact": f, "grounded": grounded})

        ungrounded = [d["fact"] for d in details if not d["grounded"]]
        return {
            "passed": len(ungrounded) == 0,
            "total_facts": len(facts),
            "ungrounded_facts": ungrounded,
            "details": details,
        }

    @classmethod
    def sanitize_output(
        cls,
        candidate_text: str,
        tool_observations: List[str],
        allowed_context: Optional[str] = None,
    ) -> str:
        """Chặn trước khi trả lời nếu có dữ kiện không có nguồn (Slide 61-62)."""
        res = cls.check_grounding(candidate_text, tool_observations, allowed_context)
        if res["passed"]:
            return candidate_text
        return (
            "CẢNH BÁO HARNESS (Grounding Violation): Câu trả lời chứa dữ kiện không có căn cứ từ dữ liệu hệ thống: "
            + ", ".join(res["ungrounded_facts"])
            + ". Đã chặn phát ngôn để tránh ảo giác (Hallucination)."
        )


# =========================================================================
# LỚP 2 · TIÊU CHÍ HOÀN THÀNH KIỂM BẰNG CODE (DETERMINISTIC VERIFICATION)
# =========================================================================
class CompletionVerifier:
    """Quy tắc lập trình khách quan được hệ thống bên ngoài kiểm chứng (Slide 43-44).

    get_booking(code).status == 'confirmed' and paid == True
    and price <= max_price and depart_date == ... and depart_time in window.
    """

    @staticmethod
    def verify_booking(booking_code: str, constraints: BookingConstraints) -> dict:
        booking = mock_db.get_booking(booking_code)
        if not booking:
            return {
                "is_completed": False,
                "error": f"Mã đặt chỗ {booking_code} không tồn tại trong hệ thống.",
                "checks": {},
            }

        checks = {
            "status_confirmed": booking.get("status") == "confirmed",
            "is_paid": booking.get("is_paid") is True,
            "has_payment_id": bool(booking.get("payment_id")),
            "price_within_budget": booking.get("price", 0) <= constraints.max_price,
            "correct_origin": booking.get("origin") == constraints.origin,
            "correct_destination": booking.get("destination") == constraints.destination,
            "correct_date": booking.get("depart_date") == constraints.depart_date,
            "correct_time_window": ConstraintValidator.is_time_in_window(
                booking.get("depart_time", ""), constraints.time_window
            ),
            "correct_passenger": booking.get("passenger_name") == constraints.passenger_name,
        }

        all_passed = all(checks.values())
        failed = [k for k, v in checks.items() if not v]

        return {
            "is_completed": all_passed,
            "booking_code": booking_code,
            "booking_record": booking,
            "checks": checks,
            "failed_reasons": failed,
        }


# =========================================================================
# LỚP 3 · KIỂM QUYỀN VÀ PHÊ DUYỆT (PERMISSION GUARD)
# =========================================================================
class PermissionStatus:
    ALLOWED = "ALLOWED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    DENIED = "DENIED"


class PermissionGuard:
    """Kiểm tra thẩm quyền trước khi thực thi tool (Pre-tool Execution Hook, Slide 35, 41).

    Chính sách:
    - Tra cứu (search, check, get_booking): Tự động cho phép.
    - Giữ chỗ / Thanh toán (book_seat, pay_ticket):
      + Nếu vé không hoàn hủy (is_refundable == False) -> Bắt buộc phê duyệt.
      + Nếu giá vé > AUTOPAY_LIMIT (mặc định 1.500.000 VNĐ) -> Bắt buộc phê duyệt.
      + pay_ticket luôn cần xác nhận của người dùng.
    """

    AUTOPAY_LIMIT = 1500000  # Ngưỡng tự động thanh toán tối đa (1.500.000đ)

    def __init__(self, autopay_limit: int = 1500000, auto_approve_test: bool = False):
        self.autopay_limit = autopay_limit
        self.auto_approve_test = auto_approve_test  # Dùng khi chạy unit test tự động
        self.approved_actions: set = set()

    def check_permission(
        self, tool_name: str, tool_args: dict, context_flight: Optional[dict] = None
    ) -> dict:
        """Kiểm tra quyền trước khi tool chạy."""
        # 1. Các tool chỉ đọc -> Luôn cấp quyền
        if tool_name in ["search_flights", "check_seat_and_fare", "get_booking_details"]:
            return {"status": PermissionStatus.ALLOWED, "reason": "Hành động tra cứu an toàn"}

        action_sig = f"{tool_name}:{repr(sorted(tool_args.items()))}"
        if action_sig in self.approved_actions or self.auto_approve_test:
            return {"status": PermissionStatus.ALLOWED, "reason": "Đã được người dùng phê duyệt"}

        # 2. Hành động book_seat
        if tool_name == "book_seat":
            flight_code = tool_args.get("flight_code", "")
            flight = context_flight or mock_db.get_flight_by_code(flight_code)

            if flight:
                reasons = []
                if not flight.get("is_refundable", True):
                    reasons.append("Vé loại KHÔNG HOÀN HỦY")
                if flight.get("price", 0) > self.autopay_limit:
                    reasons.append(
                        f"Giá vé {flight.get('price'):,}đ vượt hạn mức tự duyệt {self.autopay_limit:,}đ"
                    )

                if reasons:
                    return {
                        "status": PermissionStatus.REQUIRES_APPROVAL,
                        "action_sig": action_sig,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "where": f"Chuyến bay {flight_code} ({flight.get('airline')})",
                        "what": f"Đặt chỗ ghế chuyến {flight_code} với số tiền {flight.get('price'):,}đ",
                        "why": " & ".join(reasons),
                    }
            return {"status": PermissionStatus.ALLOWED, "reason": "Trong hạn mức cho phép"}

        # 3. Hành động pay_ticket (Thanh toán trừ tiền)
        if tool_name == "pay_ticket":
            booking_code = tool_args.get("booking_code", "")
            booking = mock_db.get_booking(booking_code)
            price = booking.get("price", 0) if booking else 0

            return {
                "status": PermissionStatus.REQUIRES_APPROVAL,
                "action_sig": action_sig,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "where": f"Đơn đặt vé {booking_code}",
                "what": f"Thực hiện giao dịch thanh toán vé số tiền {price:,}đ",
                "why": "Hành động trừ tiền tài khoản ngân hàng / thẻ tín dụng yêu cầu xác nhận",
            }

        return {"status": PermissionStatus.ALLOWED, "reason": "Hành động hợp lệ"}

    def grant_approval(self, action_sig: str):
        """Cấp quyền cho hành động đã yêu cầu."""
        self.approved_actions.add(action_sig)


# =========================================================================
# LỚP 4 · PHÁT HIỆN LẶP / BẾ TẮC VÀ BÀN GIAO (HANDOFF PROTOCOL)
# =========================================================================
class LoopDetector:
    """Bộ phát hiện lặp dựa trên Slide 45-46 và Demo 2."""

    def __init__(self, window: int = 6, repeat_k: int = 2):
        self.recent = deque(maxlen=window)
        self.repeat_k = repeat_k

    def check(self, tool: str, args: dict) -> Optional[str]:
        fp = (tool, repr(sorted(args.items())))
        cnt = self.recent.count(fp) + 1
        if cnt >= self.repeat_k:
            return f"LOOP · '{tool}' đã gọi {cnt} lần với cùng tham số trong {self.recent.maxlen} vòng gần nhất"
        self.recent.append(fp)
        return None


class StallDetector:
    """Bộ phát hiện bế tắc (Slide 40, 45, 46): tiến triển không đổi qua N vòng."""

    def __init__(self, stall_n: int = 2):
        self.stall_n = stall_n
        self.last_progress = None
        self.stall_count = 0

    def check(self, progress: Any) -> Optional[str]:
        if progress is not None:
            self.stall_count = self.stall_count + 1 if progress == self.last_progress else 0
            self.last_progress = progress

            if self.stall_count >= self.stall_n:
                return f"STALL · tiến triển đứng yên ở mức {progress!r} qua {self.stall_count} vòng liên tiếp"
        return None


class HandoffManager:
    """Bàn giao cho con người khi dừng bất thường (Slide 48, 50).

    Đảm bảo người tiếp quản có thể hiểu và ra quyết định trong vòng 30 giây.
    """

    @staticmethod
    def create_handoff_report(
        stop_reason: str,
        history_actions: List[str],
        state_summary: dict,
        question_for_human: str,
    ) -> dict:
        return {
            "stop_reason": stop_reason,
            "da_thu": history_actions,
            "trang_thai": state_summary,
            "cau_hoi_cho_nguoi": question_for_human,
        }

    @staticmethod
    def format_handoff_display(report: dict) -> str:
        lines = [
            "===================== BÁO CÁO BÀN GIAO (HANDOFF REPORT) =====================",
            f"1. LÝ DO DỪNG       : {report.get('stop_reason')}",
            f"2. CÁC BƯỚC ĐÃ THỬ  : {' -> '.join(report.get('da_thu', [])) or 'Chưa thực hiện bước nào'}",
            f"3. ẢNH CHỤP TRẠNG THÁI: {json.dumps(report.get('trang_thai', {}), ensure_ascii=False)}",
            f"4. CÂU HỎI CHO NGƯỜI: >>> {report.get('cau_hoi_cho_nguoi')} <<<",
            "=============================================================================",
        ]
        return "\n".join(lines)
