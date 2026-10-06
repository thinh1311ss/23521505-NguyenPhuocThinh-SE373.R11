# -*- coding: utf-8 -*-
"""Model giả lập tương thích LangChain/LangGraph cho bài toán đặt vé máy bay.

Hỗ trợ chạy offline 100% không tốn token, tái hiện các kịch bản chuẩn và lỗi:
- 'chuan'     : Hoàn tất trọn vẹn quy trình tìm kiếm -> kiểm tra -> đặt chỗ -> thanh toán
- 'lap'       : Lặp lại cùng một tool call để kiểm thử LoopDetector
- 'be_tac'    : Thử nhiều tool nhưng không tiến triển để kiểm thử StallDetector
- 'vuot_gia'  : Không tìm thấy chuyến bay trong ngân sách, kích hoạt bàn giao
- 'ao_giac'   : Cố tình bịa mã chuyến bay không có nguồn để kiểm thử GroundingVerifier
- 'that'      : Kết nối LLM thật từ biến môi trường qua model_that()
"""
from __future__ import annotations

import json
import os
from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ModelGiaFlight(BaseChatModel):
    """ChatModel giả lập sinh tool_calls hoặc câu trả lời theo kịch bản."""

    kich_ban: str = "chuan"
    _luot: int = 0

    @property
    def _llm_type(self) -> str:
        return "se373-flight-mock-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ModelGiaFlight":
        return self

    def _get_norm_kich_ban(self) -> str:
        return self.kich_ban.replace("-", "_")

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._luot += 1
        ai_msg = self._quyet_dinh(messages)
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    def _quyet_dinh(self, messages: List[BaseMessage]) -> AIMessage:
        """Đưa ra quyết định tiếp theo dựa trên lịch sử hội thoại."""
        kb = self._get_norm_kich_ban()

        # 1. Kịch bản cố tình gây vòng lặp (Loop Scenario)
        if kb == "lap":
            # Gọi lặp lại cùng một tool check_seat_and_fare cho VN122
            return self._tao_tool_call("check_seat_and_fare", {"flight_code": "VN122"})

        # 2. Kịch bản cố tình gây bế tắc (Stall Scenario)
        if kb == "be_tac":
            # Mỗi vòng đổi một tham số sai hoặc gọi tool khác nhưng tiến triển = 0
            codes = ["VN999", "VJ000", "QH888", "VN777", "VJ111"]
            target_code = codes[(self._luot - 1) % len(codes)]
            return self._tao_tool_call("check_seat_and_fare", {"flight_code": target_code})

        # 3. Kịch bản bịa đặt thông tin (Hallucination)
        if kb == "ao_giac":
            return AIMessage(
                content="Tôi đã tìm thấy chuyến bay QH999 của Bamboo lúc 07:00 ngày 2026-10-15 "
                        "với giá siêu rẻ chỉ 500.000đ, mã đặt vé BK-QH999-7777 đã thanh toán thành công!"
            )

        # Phân tích các observation đã có trong tin nhắn tool
        tool_observations = []
        for m in messages:
            if m.type == "tool":
                try:
                    data = json.loads(m.content) if isinstance(m.content, str) else m.content
                    tool_observations.append(data)
                except Exception:
                    tool_observations.append({"raw": m.content})

        da_search = any(obs.get("status") in ["ok", "not_found"] and "flights" in obs for obs in tool_observations)
        da_check = any("available_seats" in obs for obs in tool_observations)
        da_book = any("booking_code" in obs and obs.get("booking_status") == "pending" for obs in tool_observations)
        da_pay = any(obs.get("is_paid") is True and "payment_id" in obs for obs in tool_observations)

        # Bước 1: Chưa tìm kiếm -> Gọi search_flights
        if not da_search:
            # Phân tích nội dung user message để tìm thông tin cơ bản
            user_text = ""
            for m in messages:
                if m.type == "human":
                    user_text = m.content
                    break

            orig = "SGN" if "hcm" in user_text.lower() or "sài gòn" in user_text.lower() or "sgn" in user_text.lower() else "SGN"
            dest = "DAD" if "đà nẵng" in user_text.lower() or "dad" in user_text.lower() else "DAD"
            date = "2026-10-15"
            window = "sang" if "sáng" in user_text.lower() else ""

            return self._tao_tool_call(
                "search_flights",
                {"origin": orig, "destination": dest, "depart_date": date, "time_window": window},
            )

        # Kịch bản vượt trần giá (No Match / Over Budget)
        if kb == "vuot_gia":
            return AIMessage(
                content="Dựa trên kết quả tra cứu, tất cả các chuyến bay sáng ngày 2026-10-15 tuyến SGN-DAD "
                        "đều có giá từ 1.420.000đ trở lên, vượt trần ngân sách yêu cầu 1.200.000đ. "
                        "Tôi không thể tự ý đặt vé và cần xin ý kiến bàn giao từ quý khách."
            )

        # Bước 2: Đã search -> Kiểm tra chi tiết chuyến bay phù hợp nhất (VJ624)
        if not da_check:
            # Chọn VJ624 (giá rẻ nhất thỏa mãn: 1.420.000đ)
            return self._tao_tool_call("check_seat_and_fare", {"flight_code": "VJ624"})

        # Bước 3: Đã check -> Đặt chỗ (book_seat)
        if not da_book:
            return self._tao_tool_call(
                "book_seat",
                {
                    "flight_code": "VJ624",
                    "passenger_name": "Nguyen Van A",
                    "passenger_id": "079201009999",
                    "seat_preference": "window",
                },
            )

        # Bước 4: Đã book -> Thanh toán (pay_ticket)
        if not da_pay:
            # Lấy booking_code từ observation đặt chỗ
            booking_code = "BK-VJ624-1001"
            for obs in tool_observations:
                if "booking_code" in obs:
                    booking_code = obs["booking_code"]
                    break
            return self._tao_tool_call(
                "pay_ticket",
                {"booking_code": booking_code, "payment_method": "credit_card"},
            )

        # Bước 5: Đã thanh toán xong -> Trả lời xác nhận cuối cùng
        last_pay_info = next((obs for obs in reversed(tool_observations) if obs.get("is_paid")), {})
        b_code = last_pay_info.get("booking_code", "BK-VJ624-1001")
        f_code = last_pay_info.get("flight_code", "VJ624")
        p_name = last_pay_info.get("passenger_name", "Nguyen Van A")
        pay_id = last_pay_info.get("payment_id", "PAY-1001-OK")

        response_content = (
            f"Đã hoàn tất đặt vé máy bay thành công!\n"
            f"- Mã đặt chỗ (PNR): {b_code}\n"
            f"- Chuyến bay: {f_code} (Vietjet Air), hành trình SGN -> DAD, khởi hành 06:30 ngày 2026-10-15.\n"
            f"- Hành khách: {p_name}\n"
            f"- Tổng chi phí: 1.420.000đ (Đã thanh toán qua {pay_id}, trạng thái confirmed).\n"
            f"Vé điện tử đã được gửi tới hệ thống. Chúc quý khách có chuyến đi thuận lợi!"
        )
        return AIMessage(content=response_content)

    def _tao_tool_call(self, tool_name: str, tool_args: dict) -> AIMessage:
        cid = f"call_{tool_name}_{self._luot}"
        return AIMessage(
            content="",
            tool_calls=[{"name": tool_name, "args": tool_args, "id": cid, "type": "tool_call"}],
        )


def model_that(model_name: Optional[str] = None):
    """Khởi tạo model thật từ biến môi trường (.env).

    Tự động nhận diện nhà cung cấp:
    - Nếu là Google Gemini (hoặc endpoint googleapis): Khởi tạo ChatGoogleGenerativeAI
    - Nếu là OpenAI thông thường: Khởi tạo ChatOpenAI
    """
    from dotenv import load_dotenv
    load_dotenv()

    target_model = model_name or os.environ.get("OPENAI_MODEL") or os.environ.get("SE373_MODEL")
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "")

    if not api_key:
        raise ValueError(
            "Chưa cấu hình API Key. Vui lòng thiết lập OPENAI_API_KEY trong file .env hoặc sử dụng model giả lập."
        )

    # Nhận diện Google Gemini API để hỗ trợ thought signatures trong multi-turn tool calling
    if "generativelanguage.googleapis.com" in base_url or (target_model and "gemini" in target_model.lower()):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            m = "gemini-flash-latest" if target_model in ["gemini-3.6-flash", "gemini-2.5-flash", None] else target_model
            return ChatGoogleGenerativeAI(
                model=m,
                api_key=api_key,
                temperature=0.0,
            )
        except Exception:
            pass

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=target_model or "gpt-4o-mini",
        api_key=api_key,
        base_url=base_url if base_url else None,
        temperature=0.0,
    )
