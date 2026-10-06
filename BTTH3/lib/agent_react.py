# -*- coding: utf-8 -*-
"""Mẫu Thiết Kế 1 · ReAct Agent (Reasoning + Acting) cho Đặt Vé Máy Bay.

Chu trình cốt lõi:
    Thought -> Action (Tool Call) -> Pre-Tool Guard (Kiểm quyền)
    -> Tool Execution -> Observation -> Post-Tool Guard (Loop & Stall Detector)
    -> Thought -> ... -> Final Response -> Grounding & Completion Verifier

Ưu điểm: Phản ứng linh hoạt theo thời gian thực với kết quả của môi trường.
Nhược điểm: Chi phí token tích lũy, dễ rơi vào vòng lặp nếu không có harness bảo vệ.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.language_models import BaseChatModel

from lib.harness import (
    BookingConstraints,
    CompletionVerifier,
    GroundingVerifier,
    HandoffManager,
    LoopDetector,
    PermissionGuard,
    PermissionStatus,
    StallDetector,
)
from lib.tools_flight import get_all_flight_tools


class ReActFlightAgent:
    """Agent đặt vé máy bay theo mẫu kiến trúc ReAct kết hợp 4 lớp Harness."""

    def __init__(
        self,
        model: BaseChatModel,
        constraints: BookingConstraints,
        max_steps: int = 10,
        permission_guard: Optional[PermissionGuard] = None,
    ):
        self.model = model
        self.constraints = constraints
        self.max_steps = max_steps
        self.guard = permission_guard or PermissionGuard()
        self.loop_detector = LoopDetector(window=6, repeat_k=2)
        self.stall_detector = StallDetector(stall_n=3)
        self.tools = get_all_flight_tools()
        self.tool_map = {t.name: t for t in self.tools}
        self.bound_model = self.model.bind_tools(self.tools) if hasattr(self.model, "bind_tools") else self.model
        self.actions_taken: List[str] = []
        self.tool_observations: List[str] = []

    def run(self, user_request: str) -> dict:
        """Thực thi vòng lặp ReAct có giám sát đầy đủ bởi các lớp harness."""
        start_time = time.time()
        system_text = (
            "Bạn là trợ lý AI chuyên đặt vé máy bay nội địa chuẩn mực và an toàn.\n"
            f"Ràng buộc nghiệp vụ bắt buộc:\n"
            f"- Nơi đi: {self.constraints.origin} | Nơi đến: {self.constraints.destination}\n"
            f"- Ngày bay: {self.constraints.depart_date} | Khung giờ: buổi {self.constraints.time_window}\n"
            f"- Ngân sách tối đa: {self.constraints.max_price:,} VNĐ\n"
            f"- Hành khách: {self.constraints.passenger_name} (CCCD: {self.constraints.passenger_id})\n\n"
            "Quy trình thực thi chuẩn:\n"
            "1. Gọi `search_flights` để tìm chuyến bay.\n"
            "2. Lọc chuyến thỏa mãn đúng buổi bay và trong ngân sách.\n"
            "3. Gọi `check_seat_and_fare` để kiểm tra ghế trống chuyến đã chọn.\n"
            "4. Gọi `book_seat` để lấy mã giữ chỗ (booking code).\n"
            "5. Gọi `pay_ticket` với mã đặt chỗ để thanh toán và xuất vé.\n"
            "6. Tổng kết chi tiết mã vé, chuyến bay và giá tiền cho người dùng. Tuyệt đối không bịa số liệu."
        )
        from langchain_core.messages import SystemMessage
        messages: List[BaseMessage] = [
            SystemMessage(content=system_text),
            HumanMessage(content=user_request),
        ]
        step = 0
        total_tokens = 0
        last_booking_code = None

        while step < self.max_steps:
            step += 1

            # 1. Gọi Model để sinh Thought + Action kế tiếp
            ai_msg: AIMessage = self.bound_model.invoke(messages)
            messages.append(ai_msg)

            # Ước lượng token sử dụng (nếu model trả về token_usage thì lấy, nếu không thì ước lượng)
            usage = getattr(ai_msg, "usage_metadata", None)
            if usage:
                total_tokens += usage.get("total_tokens", 0)
            else:
                total_tokens += len(str(messages)) // 4

            # 2. Kiểm tra: Nếu model không gọi tool nữa -> Chuyển sang hoàn tất
            if not getattr(ai_msg, "tool_calls", None):
                if isinstance(ai_msg.content, list):
                    final_text = "".join(
                        c.get("text", "") if isinstance(c, dict) else str(c) for c in ai_msg.content
                    )
                else:
                    final_text = str(ai_msg.content)

                # Lớp 1: Kiểm tra Grounding (chống ảo giác số liệu)
                allowed_ctx = f"{user_request} {self.constraints.max_price} {self.constraints.origin} {self.constraints.destination} {self.constraints.depart_date}"
                grounding_res = GroundingVerifier.check_grounding(
                    final_text, self.tool_observations, allowed_context=allowed_ctx
                )
                if not grounding_res["passed"]:
                    final_text = GroundingVerifier.sanitize_output(
                        final_text, self.tool_observations, allowed_context=allowed_ctx
                    )

                # Lớp 2: Kiểm tra tiêu chí hoàn thành bằng code xác định
                completion_res = {}
                is_completed = False
                if last_booking_code:
                    completion_res = CompletionVerifier.verify_booking(
                        last_booking_code, self.constraints
                    )
                    is_completed = completion_res.get("is_completed", False)

                return {
                    "pattern": "ReAct",
                    "status": "COMPLETED" if (is_completed or "thành công" in final_text) else "STOPPED",
                    "steps": step,
                    "total_tokens": total_tokens,
                    "elapsed_time": round(time.time() - start_time, 3),
                    "final_response": final_text,
                    "messages": messages,
                    "actions_taken": self.actions_taken,
                    "completion_verified": is_completed,
                    "completion_report": completion_res,
                    "grounding_report": grounding_res,
                }

            # 3. Duyệt qua từng tool call mà Model đề xuất
            for tool_call in ai_msg.tool_calls:
                t_name = tool_call["name"]
                t_args = tool_call["args"]
                call_id = tool_call.get("id", f"call_{step}")
                act_str = f"{t_name}({t_args})"
                self.actions_taken.append(act_str)

                # -------------------------------------------------------------
                # LỚP 3: KIỂM QUYỀN TRƯỚC KHI CHẠY TOOL (PRE-TOOL EXECUTION)
                # -------------------------------------------------------------
                perm = self.guard.check_permission(t_name, t_args)
                if perm["status"] == PermissionStatus.REQUIRES_APPROVAL:
                    # Chặn lại để yêu cầu con người phê duyệt
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason="APPROVAL_REQUIRED · Hành động vượt thẩm quyền cần duyệt",
                        history_actions=self.actions_taken,
                        state_summary={
                            "current_step": step,
                            "pending_action": act_str,
                            "where": perm.get("where"),
                            "what": perm.get("what"),
                            "why": perm.get("why"),
                        },
                        question_for_human=f"Hệ thống định thực hiện: '{perm.get('what')}'. Bạn có đồng ý phê duyệt không?",
                    )
                    return {
                        "pattern": "ReAct",
                        "status": "AWAITING_APPROVAL",
                        "steps": step,
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "messages": messages,
                        "actions_taken": self.actions_taken,
                    }

                # Thực thi Tool
                tool_fn = self.tool_map.get(t_name)
                if not tool_fn:
                    obs_content = json.dumps({"status": "error", "error": f"Tool {t_name} không tồn tại"})
                else:
                    try:
                        obs_content = tool_fn.invoke(t_args)
                    except Exception as e:
                        obs_content = json.dumps({"status": "error", "error": str(e)})

                self.tool_observations.append(obs_content)
                messages.append(ToolMessage(content=str(obs_content), tool_call_id=call_id))

                # Ghi nhận mã booking nếu có
                if t_name == "book_seat":
                    try:
                        b_data = json.loads(obs_content)
                        if "booking_code" in b_data:
                            last_booking_code = b_data["booking_code"]
                    except Exception:
                        pass

                # -------------------------------------------------------------
                # LỚP 4: PHÁT HIỆN LẶP VÀ BẾ TẮC (POST-TOOL EXECUTION)
                # -------------------------------------------------------------
                loop_warn = self.loop_detector.check(t_name, t_args)
                if loop_warn:
                    handoff = HandoffManager.create_handoff_report(
                        stop_reason=loop_warn,
                        history_actions=self.actions_taken,
                        state_summary={"total_steps": step, "observations": len(self.tool_observations)},
                        question_for_human="Dịch vụ trả về lỗi liên tục hoặc cùng tham số bị lặp. Quý khách muốn thử chuyến khác hay kết nối nhân viên?",
                    )
                    return {
                        "pattern": "ReAct",
                        "status": "HANDOFF_LOOP_DETECTED",
                        "steps": step,
                        "total_tokens": total_tokens,
                        "elapsed_time": round(time.time() - start_time, 3),
                        "final_response": HandoffManager.format_handoff_display(handoff),
                        "handoff_report": handoff,
                        "messages": messages,
                        "actions_taken": self.actions_taken,
                    }

        # 4. Nếu vượt quá số bước tối đa (Hết ngân sách)
        handoff = HandoffManager.create_handoff_report(
            stop_reason=f"BUDGET_EXCEEDED · Chạm giới hạn {self.max_steps} bước tối đa",
            history_actions=self.actions_taken,
            state_summary={"steps": step, "tools_called": len(self.actions_taken)},
            question_for_human="Agent đã đạt số lượt thao tác tối đa mà chưa chốt được vé. Cần điều chỉnh tiêu chí tìm kiếm hay tiếp tục mở rộng ngân sách?",
        )
        return {
            "pattern": "ReAct",
            "status": "HANDOFF_BUDGET_EXCEEDED",
            "steps": step,
            "total_tokens": total_tokens,
            "elapsed_time": round(time.time() - start_time, 3),
            "final_response": HandoffManager.format_handoff_display(handoff),
            "handoff_report": handoff,
            "messages": messages,
            "actions_taken": self.actions_taken,
        }
