# -*- coding: utf-8 -*-
"""Mẫu Thiết Kế 2 · Plan-then-Execute Agent cho Đặt Vé Máy Bay.

Chu trình cốt lõi (Slide 22-23):
    User Goal -> Planner (Sinh toàn bộ kế hoạch từng bước)
    -> Human/Rule Review -> Executor (Thực thi tuần tự từng bước trong plan)
    -> Dynamic Parameter Resolution -> Harness Checks -> Final Completion

Ưu điểm:
    - Kế hoạch tường minh, dễ dự đoán chi phí và kiểm duyệt trước khi chạy.
    - Giảm số lượt gọi model trung gian (tiết kiệm token).
    - Giữ vững mục tiêu ban đầu (hạn chế tối đa goal drift).

Nhược điểm:
    - Kém linh hoạt khi môi trường thay đổi bất ngờ nếu không có cơ chế replan.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

from lib.harness import (
    BookingConstraints,
    CompletionVerifier,
    ConstraintValidator,
    GroundingVerifier,
    HandoffManager,
    PermissionGuard,
    PermissionStatus,
)
from lib.tools_flight import get_all_flight_tools


class PlanThenExecuteFlightAgent:
    """Agent đặt vé máy bay theo mẫu Plan-then-Execute kết hợp 4 lớp Harness."""

    def __init__(
        self,
        model: BaseChatModel,
        constraints: BookingConstraints,
        permission_guard: Optional[PermissionGuard] = None,
    ):
        self.model = model
        self.constraints = constraints
        self.guard = permission_guard or PermissionGuard()
        self.tool_map = {t.name: t for t in get_all_flight_tools()}
        self.actions_taken: List[str] = []
        self.tool_observations: List[str] = []

    def _generate_plan(self, user_request: str) -> List[dict]:
        """Bước 1: Lập kế hoạch tuần tự dựa trên yêu cầu và ràng buộc bài toán."""
        # Kế hoạch chuẩn 4 bước cho bài toán đặt vé máy bay
        return [
            {
                "step_id": 1,
                "name": "Tìm kiếm chuyến bay",
                "tool": "search_flights",
                "args_template": {
                    "origin": self.constraints.origin,
                    "destination": self.constraints.destination,
                    "depart_date": self.constraints.depart_date,
                    "time_window": self.constraints.time_window,
                },
            },
            {
                "step_id": 2,
                "name": "Kiểm tra ghế & giá chuyến bay tối ưu",
                "tool": "check_seat_and_fare",
                "args_template": {"flight_code": "$SELECTED_FLIGHT"},
            },
            {
                "step_id": 3,
                "name": "Giữ chỗ đặt vé",
                "tool": "book_seat",
                "args_template": {
                    "flight_code": "$SELECTED_FLIGHT",
                    "passenger_name": self.constraints.passenger_name,
                    "passenger_id": self.constraints.passenger_id,
                    "seat_preference": "window",
                },
            },
            {
                "step_id": 4,
                "name": "Thanh toán & Xuất vé",
                "tool": "pay_ticket",
                "args_template": {
                    "booking_code": "$BOOKING_CODE",
                    "payment_method": "credit_card",
                },
            },
        ]

    def run(self, user_request: str) -> dict:
        """Thực thi kế hoạch tuần tự kèm theo kiểm tra harness ở từng bước."""
        start_time = time.time()
        plan = self._generate_plan(user_request)
        total_tokens = 0

        # Gọi model 1 lần để xác nhận kế hoạch (ước lượng token)
        plan_prompt = f"Lập kế hoạch đặt vé máy bay cho yêu cầu: {user_request}"
        ai_plan = self.model.invoke([HumanMessage(content=plan_prompt)])
        usage = getattr(ai_plan, "usage_metadata", None)
        if usage:
            total_tokens += usage.get("total_tokens", 0)
        else:
            total_tokens += 120

        # Context pipeline lưu trữ kết quả qua các bước
        context = {
            "selected_flight": None,
            "booking_code": None,
            "flight_data": None,
        }

        for step in plan:
            t_name = step["tool"]
            raw_args = step["args_template"].copy()

            # Phân giải tham số động (Dynamic Parameter Resolution)
            if raw_args.get("flight_code") == "$SELECTED_FLIGHT":
                if not context["selected_flight"]:
                    # Nếu chưa chọn được chuyến bay hợp lệ -> Bế tắc -> Bàn giao
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason="PLAN_EXECUTION_STALL · Chưa xác định được chuyến bay hợp lệ cho bước 2",
                        history_actions=self.actions_taken,
                        state_summary={"failed_step": step["step_id"], "plan": plan},
                        question_for_human="Không tìm thấy chuyến bay phù hợp với tiêu chí ngân sách. Bạn có muốn đổi giờ bay hay tăng ngân sách?",
                    )
                    return {
                        "pattern": "Plan-then-Execute",
                        "status": "HANDOFF_NO_MATCH",
                        "steps": step["step_id"],
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "plan": plan,
                        "actions_taken": self.actions_taken,
                    }
                raw_args["flight_code"] = context["selected_flight"]

            if raw_args.get("booking_code") == "$BOOKING_CODE":
                if not context["booking_code"]:
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason="PLAN_EXECUTION_ERROR · Thiếu mã đặt chỗ cho bước thanh toán",
                        history_actions=self.actions_taken,
                        state_summary={"failed_step": step["step_id"]},
                        question_for_human="Chưa tạo được mã giữ chỗ. Có muốn thử đặt lại chuyến bay khác?",
                    )
                    return {
                        "pattern": "Plan-then-Execute",
                        "status": "HANDOFF_ERROR",
                        "steps": step["step_id"],
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "plan": plan,
                        "actions_taken": self.actions_taken,
                    }
                raw_args["booking_code"] = context["booking_code"]

            act_str = f"{t_name}({raw_args})"
            self.actions_taken.append(act_str)

            # -------------------------------------------------------------
            # LỚP 3: KIỂM QUYỀN TRƯỚC KHI CHẠY BƯỚC CỦA KẾ HOẠCH
            # -------------------------------------------------------------
            perm = self.guard.check_permission(t_name, raw_args, context_flight=context.get("flight_data"))
            if perm["status"] == PermissionStatus.REQUIRES_APPROVAL:
                handoff = HandoffManager.create_handoff_report(
                    stop_reason="APPROVAL_REQUIRED · Bước trong kế hoạch cần phê duyệt",
                    history_actions=self.actions_taken,
                    state_summary={
                        "step_id": step["step_id"],
                        "plan_name": step["name"],
                        "pending_action": act_str,
                        "where": perm.get("where"),
                        "what": perm.get("what"),
                        "why": perm.get("why"),
                    },
                    question_for_human=f"Kế hoạch chuẩn bị thực hiện: '{perm.get('what')}'. Bạn có đồng ý phê duyệt tiếp tục?",
                )
                return {
                    "pattern": "Plan-then-Execute",
                    "status": "AWAITING_APPROVAL",
                    "steps": step["step_id"],
                    "total_tokens": total_tokens,
                    "elapsed_time": round(time.time() - start_time, 3),
                    "final_response": HandoffManager.format_handoff_display(handoff),
                    "handoff_report": handoff,
                    "plan": plan,
                    "actions_taken": self.actions_taken,
                }

            # Thực thi tool
            tool_fn = self.tool_map.get(t_name)
            try:
                obs_content = tool_fn.invoke(raw_args)
            except Exception as e:
                obs_content = json.dumps({"status": "error", "error": str(e)})

            self.tool_observations.append(obs_content)

            # Phân tích kết quả observation để cập nhật context pipeline
            try:
                obs_data = json.loads(obs_content)
            except Exception:
                obs_data = {}

            # Nếu tool trả về lỗi (ví dụ timeout, service unavailable) -> Kích hoạt Handoff
            if obs_data.get("status") == "error":
                handoff = HandoffManager.create_handoff_report(
                    stop_reason=f"TOOL_ERROR · {obs_data.get('error_code', 'ERROR')}: {obs_data.get('message', 'Lỗi thực thi tool')}",
                    history_actions=self.actions_taken,
                    state_summary={"failed_step": step["step_id"], "tool": t_name},
                    question_for_human=f"Dịch vụ tại bước '{step['name']}' gặp lỗi. Bạn muốn thử lại hay chuyển nhân viên xử lý?",
                )
                return {
                    "pattern": "Plan-then-Execute",
                    "status": "HANDOFF_ERROR",
                    "steps": step["step_id"],
                    "total_tokens": total_tokens,
                    "elapsed_time": round(time.time() - start_time, 3),
                    "final_response": HandoffManager.format_handoff_display(handoff),
                    "handoff_report": handoff,
                    "plan": plan,
                    "actions_taken": self.actions_taken,
                }

            # Nếu bước 1 (search_flights): chọn chuyến bay thỏa mãn ràng buộc
            if t_name == "search_flights":
                flights = obs_data.get("flights", [])
                valid_flights = []
                for f in flights:
                    valid, _ = ConstraintValidator.validate_flight(f, self.constraints)
                    if valid:
                        valid_flights.append(f)

                if not valid_flights:
                    # Ràng buộc là dữ liệu: phát hiện ngay không có chuyến thỏa mãn!
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason="CONSTRAINT_VIOLATION · Không có chuyến bay nào thỏa mãn trần giá và khung giờ",
                        history_actions=self.actions_taken,
                        state_summary={
                            "total_matched": len(flights),
                            "constraints": self.constraints.to_dict(),
                        },
                        question_for_human=f"Tất cả chuyến bay đều vượt ngân sách {self.constraints.max_price:,}đ. Quý khách có muốn tăng ngân sách hoặc đổi sang buổi khác?",
                    )
                    return {
                        "pattern": "Plan-then-Execute",
                        "status": "HANDOFF_CONSTRAINT_VIOLATION",
                        "steps": step["step_id"],
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "plan": plan,
                        "actions_taken": self.actions_taken,
                    }

                # Chọn chuyến bay có giá tốt nhất
                valid_flights.sort(key=lambda x: x["price"])
                chosen = valid_flights[0]
                context["selected_flight"] = chosen["flight_code"]
                context["flight_data"] = chosen

            elif t_name == "book_seat":
                context["booking_code"] = obs_data.get("booking_code")

        # Hoàn tất toàn bộ các bước trong plan -> Tổng hợp kết quả
        b_code = context["booking_code"]

        # Lớp 2: Kiểm tra tiêu chí hoàn thành bằng code xác định
        comp_res = CompletionVerifier.verify_booking(b_code, self.constraints)

        final_msg = (
            f"Kế hoạch đặt vé máy bay đã thực thi hoàn tất 100%:\n"
            f"- Mã đặt chỗ: {b_code}\n"
            f"- Chuyến bay: {context['selected_flight']}\n"
            f"- Trạng thái: confirmed (Đã thanh toán)\n"
            f"- Tiêu chí hoàn thành code: {'ĐẠT' if comp_res['is_completed'] else 'KHÔNG ĐẠT'}"
        )

        # Lớp 1: Kiểm tra Grounding
        grounding_res = GroundingVerifier.check_grounding(final_msg, self.tool_observations)

        return {
            "pattern": "Plan-then-Execute",
            "status": "COMPLETED" if comp_res["is_completed"] else "VERIFICATION_FAILED",
            "steps": len(plan),
            "total_tokens": total_tokens,
            "elapsed_time": round(time.time() - start_time, 3),
            "final_response": final_msg,
            "plan": plan,
            "actions_taken": self.actions_taken,
            "completion_verified": comp_res["is_completed"],
            "completion_report": comp_res,
            "grounding_report": grounding_res,
        }
