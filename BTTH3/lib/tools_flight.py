# -*- coding: utf-8 -*-
"""Bộ Tool Mockup cho Agent Đặt Vé Máy Bay (LangChain / LangGraph Tools).

Cung cấp 5 tool thao tác với hệ thống chuyến bay, có hỗ trợ:
1. Chuẩn hóa tên thành phố / sân bay tự động (Sài Gòn -> SGN, Đà Nẵng -> DAD)
2. Trả về cấu trúc JSON chuẩn hóa (observation có cấu trúc)
3. Chế độ giả lập lỗi môi trường (SE373_FLIGHT_ERROR=1) để kiểm thử điều kiện dừng
"""
import os
import json
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from lib.mock_flight_db import mock_db, AIRPORTS


# Bản đồ chuẩn hóa tên địa phương sang mã sân bay IATA
CITY_TO_IATA = {
    "sgn": "SGN",
    "tp.hcm": "SGN",
    "tphcm": "SGN",
    "tp hcm": "SGN",
    "hồ chí minh": "SGN",
    "ho chi minh": "SGN",
    "sài gòn": "SGN",
    "sai gon": "SGN",
    "dad": "DAD",
    "đà nẵng": "DAD",
    "da nang": "DAD",
    "han": "HAN",
    "hà nội": "HAN",
    "ha noi": "HAN",
    "cxr": "CXR",
    "cam ranh": "CXR",
    "nha trang": "CXR",
    "pqc": "PQC",
    "phú quốc": "PQC",
    "phu quoc": "PQC",
}


def _normalize_airport(location_str: str) -> str:
    """Chuẩn hóa chuỗi địa danh hoặc mã IATA sang mã IATA 3 ký tự."""
    s = location_str.strip().lower()
    return CITY_TO_IATA.get(s, location_str.strip().upper())


def _is_simulated_error() -> bool:
    """Kiểm tra biến môi trường giả lập sự cố hệ thống dịch vụ vé."""
    return os.environ.get("SE373_FLIGHT_ERROR") == "1"


# =========================================================================
# TOOL 1: Tìm kiếm chuyến bay
# =========================================================================
@tool
def search_flights(origin: str, destination: str, depart_date: str, time_window: str = "") -> str:
    """Tìm danh sách chuyến bay theo nơi đi, nơi đến, ngày bay và buổi bay.

    Args:
        origin: Mã sân bay hoặc tên thành phố khởi hành (ví dụ: 'SGN', 'TP.HCM').
        destination: Mã sân bay hoặc tên thành phố hạ cánh (ví dụ: 'DAD', 'Đà Nẵng').
        depart_date: Ngày bay định dạng 'YYYY-MM-DD' (ví dụ: '2026-10-15').
        time_window: Khung giờ muốn bay: 'sang' (sáng 05:00-11:59), 'chieu' (chiều 12:00-17:59), 'toi' (tối 18:00-23:59), hoặc để trống nếu tìm mọi giờ.
    """
    if _is_simulated_error():
        return json.dumps({
            "status": "error",
            "error_code": "SERVICE_TIMEOUT",
            "message": "Cổng kết nối GDS đối tác phản hồi timeout sau 5000ms. Vui lòng thử lại sau.",
        }, ensure_ascii=False)

    orig_code = _normalize_airport(origin)
    dest_code = _normalize_airport(destination)

    # Kiểm tra mã sân bay hợp lệ
    if orig_code not in AIRPORTS or dest_code not in AIRPORTS:
        return json.dumps({
            "status": "error",
            "error_code": "INVALID_AIRPORT",
            "message": f"Tuyến bay giữa '{origin}' và '{destination}' không được hỗ trợ.",
            "supported_airports": {code: name for code, name in AIRPORTS.items()},
        }, ensure_ascii=False)

    flights = mock_db.search_flights(
        origin=orig_code,
        destination=dest_code,
        depart_date=depart_date,
        time_window=time_window.strip().lower() if time_window else None,
    )

    if not flights:
        return json.dumps({
            "status": "not_found",
            "message": f"Không có chuyến bay nào từ {orig_code} đi {dest_code} vào ngày {depart_date} {f'buổi {time_window}' if time_window else ''}.",
            "flights": [],
            "matched_count": 0,
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "origin": orig_code,
        "destination": dest_code,
        "depart_date": depart_date,
        "matched_count": len(flights),
        "flights": flights,
    }, ensure_ascii=False)


# =========================================================================
# TOOL 2: Kiểm tra chi tiết giá và ghế
# =========================================================================
@tool
def check_seat_and_fare(flight_code: str) -> str:
    """Kiểm tra chi tiết tình trạng ghế trống, mức giá vé và điều kiện hoàn hủy của chuyến bay.

    Args:
        flight_code: Mã chuyến bay (ví dụ: 'VN122', 'VJ624', 'QH150').
    """
    code = flight_code.strip().upper()
    flight = mock_db.get_flight_by_code(code)

    if not flight:
        return json.dumps({
            "status": "error",
            "error_code": "FLIGHT_NOT_FOUND",
            "message": f"Không tìm thấy chuyến bay có mã {code}. Vui lòng gọi search_flights để xem danh sách chuyến bay hợp lệ.",
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "flight_code": flight["flight_code"],
        "airline": flight["airline"],
        "price": flight["price"],
        "formatted_price": f"{flight['price']:,} VNĐ",
        "available_seats": flight["available_seats"],
        "is_refundable": flight["is_refundable"],
        "refund_policy": "Được hoàn/hủy vé có tính phí" if flight["is_refundable"] else "Vé khuyến mãi KHÔNG HOÀN HỦY",
        "baggage": flight["baggage"],
        "depart_time": flight["depart_time"],
        "arrive_time": flight["arrive_time"],
    }, ensure_ascii=False)


# =========================================================================
# TOOL 3: Giữ chỗ đặt vé (Book Seat)
# =========================================================================
@tool
def book_seat(flight_code: str, passenger_name: str, passenger_id: str, seat_preference: str = "window") -> str:
    """Tạo lệnh giữ chỗ cho hành khách trên chuyến bay (trạng thái pending chờ thanh toán).

    Lưu ý: Hành động này có tác dụng phụ (giữ ghế trong kho), cần đảm bảo đúng thông tin trước khi gọi.

    Args:
        flight_code: Mã chuyến bay muốn đặt (ví dụ: 'VJ624').
        passenger_name: Họ và tên hành khách (ví dụ: 'Nguyen Van A').
        passenger_id: Số CMND/CCCD hoặc Hộ chiếu hành khách.
        seat_preference: Sở thích vị trí ghế: 'window' (cửa sổ), 'aisle' (lối đi), hoặc 'any'.
    """
    code = flight_code.strip().upper()
    try:
        booking = mock_db.create_booking(
            flight_code=code,
            passenger_name=passenger_name,
            passenger_id=passenger_id,
            seat_preference=seat_preference,
        )
        return json.dumps({
            "status": "success",
            "message": "Giữ chỗ thành công. Vui lòng thanh toán để xác nhận vé.",
            "booking_code": booking["booking_code"],
            "flight_code": booking["flight_code"],
            "airline": booking["airline"],
            "price": booking["price"],
            "formatted_price": f"{booking['price']:,} VNĐ",
            "passenger_name": booking["passenger_name"],
            "booking_status": booking["status"],
            "is_refundable": booking["is_refundable"],
            "is_paid": booking["is_paid"],
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error_code": "BOOKING_FAILED",
            "message": str(e),
        }, ensure_ascii=False)


# =========================================================================
# TOOL 4: Thanh toán và xuất vé (Pay Ticket)
# =========================================================================
@tool
def pay_ticket(booking_code: str, payment_method: str = "credit_card") -> str:
    """Thực hiện thanh toán cho mã đơn đặt chỗ để chuyển trạng thái sang xác nhận (confirmed).

    LƯU Ý QUAN TRỌNG: Đây là hành động nhạy cảm tài chính (trừ tiền), bắt buộc phải có thẩm quyền phê duyệt.

    Args:
        booking_code: Mã đặt chỗ đã được cấp từ tool book_seat (ví dụ: 'BK-VJ624-1001').
        payment_method: Phương thức thanh toán (ví dụ: 'credit_card', 'bank_transfer', 'momo').
    """
    code = booking_code.strip().upper()
    try:
        booking = mock_db.pay_booking(code, payment_method=payment_method)
        return json.dumps({
            "status": "success",
            "message": "Thanh toán thành công. Vé máy bay điện tử đã được xác nhận!",
            "booking_code": booking["booking_code"],
            "flight_code": booking["flight_code"],
            "passenger_name": booking["passenger_name"],
            "price": booking["price"],
            "booking_status": booking["status"],
            "is_paid": booking["is_paid"],
            "payment_id": booking["payment_id"],
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error_code": "PAYMENT_FAILED",
            "message": str(e),
        }, ensure_ascii=False)


# =========================================================================
# TOOL 5: Tra cứu chi tiết đơn đặt vé
# =========================================================================
@tool
def get_booking_details(booking_code: str) -> str:
    """Truy vấn thông tin chi tiết và trạng thái hiện tại của một mã đơn đặt vé.

    Args:
        booking_code: Mã đặt chỗ (ví dụ: 'BK-VJ624-1001').
    """
    code = booking_code.strip().upper()
    booking = mock_db.get_booking(code)
    if not booking:
        return json.dumps({
            "status": "error",
            "error_code": "BOOKING_NOT_FOUND",
            "message": f"Không tìm thấy thông tin đơn đặt vé với mã '{code}'.",
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "booking": booking,
    }, ensure_ascii=False)


def get_all_flight_tools():
    """Trả về danh sách 5 tools dành cho LangChain / LangGraph Agent."""
    return [
        search_flights,
        check_seat_and_fare,
        book_seat,
        pay_ticket,
        get_booking_details,
    ]
