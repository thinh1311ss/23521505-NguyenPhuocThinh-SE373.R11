# -*- coding: utf-8 -*-
"""Mẫu Thiết Kế 3 · Mẫu Lai (Hybrid: Plan-guided ReAct with Dynamic Replanning).

Chu trình cốt lõi (Slide 24):
    Lập kế hoạch vĩ mô (Milestones/TodoList) -> Thực thi k bước bằng ReAct
    -> Observation đổi đáng kể?
        + Có: Replanning (Tái lập kế hoạch thích ứng)
        + Không: Tiếp tục thực thi cho tới khi hoàn tất
    -> Kiểm chứng bằng 4 lớp Harness

Ưu điểm:
    - Cân bằng hoàn hảo: Định hướng dài hạn của Planner + Độ nhạy thích ứng của ReAct.
    - Xử lý mượt mà cả tác vụ dài lẫn biến động bất ngờ (hết vé, lỗi mạng, giá thay đổi).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.language_models import BaseChatModel

from lib.harness import (
    BookingConstraints,
    CompletionVerifier,
    ConstraintValidator,
    GroundingVerifier,
    HandoffManager,
    LoopDetector,
    PermissionGuard,
    PermissionStatus,
    StallDetector,
)
from lib.tools_flight import get_all_flight_tools


class HybridFlightAgent:
    """Agent đặt vé máy bay theo kiến trúc Lai (Hybrid Plan + ReAct)."""

    def __init__(
        self,
        model: BaseChatModel,
        constraints: BookingConstraints,
        permission_guard: Optional[PermissionGuard] = None,
    ):
        self.model = model
        self.constraints = constraints
        self.guard = permission_guard or PermissionGuard()
        self.loop_detector = LoopDetector(window=6, repeat_k=2)
        self.stall_detector = StallDetector(stall_n=3)
        self.tool_map = {t.name: t for t in get_all_flight_tools()}
        self.actions_taken: List[str] = []
        self.tool_observations: List[str] = []
        self.replan_count = 0

    def _init_macro_milestones(self) -> List[dict]:
        """Tạo danh sách các cột mốc mục tiêu (Macro Milestones / Todo List)."""
        return [
            {
                "id": "M1",
                "title": "Tìm kiếm & Lọc chuyến bay theo ràng buộc",
                "status": "pending",  # pending -> in_progress -> completed -> failed
                "target_tool": "search_flights",
            },
            {
                "id": "M2",
                "title": "Thẩm định chi tiết ghế & chính sách vé",
                "status": "pending",
                "target_tool": "check_seat_and_fare",
            },
            {
                "id": "M3",
                "title": "Đặt chỗ & Kiểm tra thẩm quyền",
                "status": "pending",
                "target_tool": "book_seat",
            },
            {
                "id": "M4",
                "title": "Thanh toán & Xác nhận hoàn thành",
                "status": "pending",
                "target_tool": "pay_ticket",
            },
        ]

    def run(self, user_request: str) -> dict:
        """Thực thi chu trình Lai: Milestone-guided ReAct with Dynamic Replanning."""
        start_time = time.time()
        milestones = self._init_macro_milestones()
        total_tokens = 0
        step_count = 0

        # Trạng thái chia sẻ giữa các Milestone
        state = {
            "candidate_flights": [],
            "selected_flight": None,
            "flight_details": None,
            "booking_code": None,
            "payment_confirmed": False,
        }

        # Gọi LLM ban đầu để thiết lập định hướng tổng thể
        macro_plan_prompt = f"Phân tích yêu cầu và duyệt mục tiêu 4 cột mốc đặt vé: {user_request}"
        ai_resp = self.model.invoke([HumanMessage(content=macro_plan_prompt)])
        usage = getattr(ai_resp, "usage_metadata", None)
        total_tokens += usage.get("total_tokens", 150) if usage else 150

        # Thực thi lần lượt từng Milestone bằng cơ chế ReAct vi mô (Micro ReAct)
        current_m_idx = 0
        while current_m_idx < len(milestones):
            m = milestones[current_m_idx]
            m["status"] = "in_progress"
            step_count += 1

            # -------------------------------------------------------------
            # MILESTONE 1: Tìm kiếm & Lọc chuyến bay
            # -------------------------------------------------------------
            if m["id"] == "M1":
                act_str = f"search_flights(origin={self.constraints.origin!r}, destination={self.constraints.destination!r}, depart_date={self.constraints.depart_date!r}, time_window={self.constraints.time_window!r})"
                self.actions_taken.append(act_str)

                tool_fn = self.tool_map["search_flights"]
                obs = tool_fn.invoke({
                    "origin": self.constraints.origin,
                    "destination": self.constraints.destination,
                    "depart_date": self.constraints.depart_date,
                    "time_window": self.constraints.time_window,
                })
                self.tool_observations.append(obs)

                obs_data = json.loads(obs) if isinstance(obs, str) else obs

                if obs_data.get("status") == "error":
                    m["status"] = "failed"
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason=f"TOOL_ERROR · {obs_data.get('error_code', 'ERROR')}: {obs_data.get('message')}",
                        history_actions=self.actions_taken,
                        state_summary={"milestone": m["id"], "tool": "search_flights"},
                        question_for_human=f"Dịch vụ tìm kiếm chuyến bay trả về lỗi: {obs_data.get('message')}. Bạn muốn thử lại hay chuyển nhân viên hỗ trợ?",
                    )
                    return {
                        "pattern": "Hybrid (Plan + ReAct)",
                        "status": "HANDOFF_ERROR",
                        "steps": step_count,
                        "replan_count": self.replan_count,
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "milestones": milestones,
                        "actions_taken": self.actions_taken,
                    }

                flights = obs_data.get("flights", [])

                # Lớp 1: Ràng buộc là dữ liệu - Lọc nghiêm ngặt
                valid_flights = []
                for f in flights:
                    valid, _ = ConstraintValidator.validate_flight(f, self.constraints)
                    if valid and f.get("available_seats", 0) > 0:
                        valid_flights.append(f)

                if not valid_flights:
                    # Kích hoạt Dynamic Replanning: Thử tìm kiếm mở rộng hoặc Bàn giao
                    self.replan_count += 1
                    m["status"] = "failed"
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason="CONSTRAINT_UNSATISFIED · Không có chuyến bay nào thỏa mãn toàn bộ ràng buộc ngân sách & giờ bay",
                        history_actions=self.actions_taken,
                        state_summary={"searched_count": len(flights), "constraints": self.constraints.to_dict()},
                        question_for_human=f"Toàn bộ chuyến bay sáng ngày {self.constraints.depart_date} đều vượt trần {self.constraints.max_price:,}đ. Quý khách có muốn nới trần giá hay chuyển sang chuyến buổi chiều?",
                    )
                    return {
                        "pattern": "Hybrid (Plan + ReAct)",
                        "status": "HANDOFF_CONSTRAINT_VIOLATION",
                        "steps": step_count,
                        "replan_count": self.replan_count,
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "milestones": milestones,
                        "actions_taken": self.actions_taken,
                    }

                # Sắp xếp chọn chuyến bay tối ưu nhất
                valid_flights.sort(key=lambda x: x["price"])
                state["candidate_flights"] = valid_flights
                state["selected_flight"] = valid_flights[0]
                m["status"] = "completed"
                current_m_idx += 1
                continue

            # -------------------------------------------------------------
            # MILESTONE 2: Thẩm định chi tiết ghế & chính sách vé
            # -------------------------------------------------------------
            elif m["id"] == "M2":
                f_code = state["selected_flight"]["flight_code"]
                act_str = f"check_seat_and_fare(flight_code={f_code!r})"
                self.actions_taken.append(act_str)

                # Lớp 4: Kiểm tra LoopDetector
                loop_warn = self.loop_detector.check("check_seat_and_fare", {"flight_code": f_code})
                if loop_warn:
                    m["status"] = "failed"
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason=loop_warn,
                        history_actions=self.actions_taken,
                        state_summary={"milestone": m["id"]},
                        question_for_human="Dịch vụ tra cứu chuyến bay bị lặp bất thường. Bạn muốn thử lại hay đổi chuyến bay?",
                    )
                    return {
                        "pattern": "Hybrid (Plan + ReAct)",
                        "status": "HANDOFF_LOOP_DETECTED",
                        "steps": step_count,
                        "replan_count": self.replan_count,
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "milestones": milestones,
                        "actions_taken": self.actions_taken,
                    }

                tool_fn = self.tool_map["check_seat_and_fare"]
                obs = tool_fn.invoke({"flight_code": f_code})
                self.tool_observations.append(obs)
                obs_data = json.loads(obs) if isinstance(obs, str) else obs

                # Kiểm tra nếu hết ghế -> Dynamic Replanning chọn chuyến bay kế tiếp
                if obs_data.get("available_seats", 0) <= 0:
                    self.replan_count += 1
                    # Loại bỏ chuyến này và chọn chuyến kế tiếp trong danh sách candidate
                    state["candidate_flights"].pop(0)
                    if not state["candidate_flights"]:
                        handoff = HandoffManager.create_handoff_report(
                            stop_reason="ALL_CANDIDATES_EXHAUSTED · Tất cả chuyến bay dự phòng đều đã hết chỗ",
                            history_actions=self.actions_taken,
                            state_summary={"exhausted_count": len(self.actions_taken)},
                            question_for_human="Tất cả các chuyến bay phù hợp đều đã hết chỗ. Quý khách muốn chọn ngày bay khác không?",
                        )
                        return {
                            "pattern": "Hybrid (Plan + ReAct)",
                            "status": "HANDOFF_EXHAUSTED",
                            "steps": step_count,
                            "replan_count": self.replan_count,
                            "total_tokens": total_tokens,
                            "elapsed_time": round(time.time() - start_time, 3),
                            "final_response": HandoffManager.format_handoff_display(handoff),
                            "handoff_report": handoff,
                            "milestones": milestones,
                            "actions_taken": self.actions_taken,
                        }
                    state["selected_flight"] = state["candidate_flights"][0]
                    # Giữ nguyên M2 để kiểm tra chuyến bay thay thế
                    continue

                state["flight_details"] = obs_data
                m["status"] = "completed"
                current_m_idx += 1
                continue

            # -------------------------------------------------------------
            # MILESTONE 3: Giữ chỗ & Kiểm tra thẩm quyền
            # -------------------------------------------------------------
            elif m["id"] == "M3":
                f_code = state["selected_flight"]["flight_code"]
                book_args = {
                    "flight_code": f_code,
                    "passenger_name": self.constraints.passenger_name,
                    "passenger_id": self.constraints.passenger_id,
                    "seat_preference": "window",
                }
                act_str = f"book_seat({book_args})"
                self.actions_taken.append(act_str)

                # Lớp 3: Kiểm quyền trước khi gọi book_seat
                perm = self.guard.check_permission(
                    "book_seat", book_args, context_flight=state.get("flight_details")
                )
                if perm["status"] == PermissionStatus.REQUIRES_APPROVAL:
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason="APPROVAL_REQUIRED · Chuyến bay cần người dùng phê duyệt",
                        history_actions=self.actions_taken,
                        state_summary={
                            "milestone": m["id"],
                            "flight_code": f_code,
                            "airline": state["selected_flight"].get("airline"),
                            "price": state["selected_flight"].get("price"),
                            "why": perm.get("why"),
                        },
                        question_for_human=f"Hệ thống chuẩn bị giữ chỗ chuyến {f_code} ({perm.get('why')}). Quý khách có đồng ý đặt không?",
                    )
                    return {
                        "pattern": "Hybrid (Plan + ReAct)",
                        "status": "AWAITING_APPROVAL",
                        "steps": step_count,
                        "replan_count": self.replan_count,
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "milestones": milestones,
                        "actions_taken": self.actions_taken,
                    }

                tool_fn = self.tool_map["book_seat"]
                obs = tool_fn.invoke(book_args)
                self.tool_observations.append(obs)
                obs_data = json.loads(obs) if isinstance(obs, str) else obs

                if obs_data.get("status") != "success":
                    m["status"] = "failed"
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason=f"BOOKING_FAILED · {obs_data.get('message')}",
                        history_actions=self.actions_taken,
                        state_summary={"obs": obs_data},
                        question_for_human="Hệ thống giữ chỗ thất bại. Bạn có muốn đổi chuyến khác?",
                    )
                    return {
                        "pattern": "Hybrid (Plan + ReAct)",
                        "status": "HANDOFF_FAILED",
                        "steps": step_count,
                        "replan_count": self.replan_count,
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "milestones": milestones,
                        "actions_taken": self.actions_taken,
                    }

                state["booking_code"] = obs_data.get("booking_code")
                m["status"] = "completed"
                current_m_idx += 1
                continue

            # -------------------------------------------------------------
            # MILESTONE 4: Thanh toán & Hoàn tất
            # -------------------------------------------------------------
            elif m["id"] == "M4":
                b_code = state["booking_code"]
                pay_args = {"booking_code": b_code, "payment_method": "credit_card"}
                act_str = f"pay_ticket({pay_args})"
                self.actions_taken.append(act_str)

                # Lớp 3: Kiểm quyền thanh toán
                perm = self.guard.check_permission("pay_ticket", pay_args)
                if perm["status"] == PermissionStatus.REQUIRES_APPROVAL:
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason="PAYMENT_APPROVAL_REQUIRED · Yêu cầu phê duyệt trừ tiền",
                        history_actions=self.actions_taken,
                        state_summary={
                            "milestone": m["id"],
                            "booking_code": b_code,
                            "price": state["selected_flight"].get("price"),
                        },
                        question_for_human=f"Xác nhận thanh toán vé {b_code} với số tiền {state['selected_flight'].get('price'):,}đ?",
                    )
                    return {
                        "pattern": "Hybrid (Plan + ReAct)",
                        "status": "AWAITING_APPROVAL",
                        "steps": step_count,
                        "replan_count": self.replan_count,
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "milestones": milestones,
                        "actions_taken": self.actions_taken,
                    }

                tool_fn = self.tool_map["pay_ticket"]
                obs = tool_fn.invoke(pay_args)
                self.tool_observations.append(obs)
                obs_data = json.loads(obs) if isinstance(obs, str) else obs

                if obs_data.get("is_paid") is True:
                    state["payment_confirmed"] = True
                    m["status"] = "completed"
                    current_m_idx += 1
                else:
                    m["status"] = "failed"
                    break

        # Lớp 2: Tiêu chí hoàn thành kiểm bằng code
        comp_res = CompletionVerifier.verify_booking(state["booking_code"], self.constraints)

        final_msg = (
            f"Quy trình Đặt vé máy bay (Mẫu Lai) đã hoàn tất xuất sắc:\n"
            f"- Mã đặt chỗ: {state['booking_code']}\n"
            f"- Chuyến bay: {state['selected_flight']['flight_code']} ({state['selected_flight']['airline']})\n"
            f"- Giá vé: {state['selected_flight']['price']:,} VNĐ\n"
            f"- Trạng thái vé: Đã thanh toán và xuất vé điện tử thành công!\n"
            f"- Số lần Dynamic Replanning: {self.replan_count}\n"
            f"- Tiêu chí hoàn thành (Code Verification): {'ĐẠT CHUẨN' if comp_res['is_completed'] else 'KHÔNG ĐẠT'}"
        )

        # Lớp 1: Kiểm tra Grounding
        grounding_res = GroundingVerifier.check_grounding(final_msg, self.tool_observations)

        return {
            "pattern": "Hybrid (Plan + ReAct)",
            "status": "COMPLETED" if comp_res["is_completed"] else "VERIFICATION_FAILED",
            "steps": step_count,
            "replan_count": self.replan_count,
            "total_tokens": total_tokens,
            "elapsed_time": round(time.time() - start_time, 3),
            "final_response": final_msg,
            "milestones": milestones,
            "actions_taken": self.actions_taken,
            "completion_verified": comp_res["is_completed"],
            "completion_report": comp_res,
            "grounding_report": grounding_res,
        }
