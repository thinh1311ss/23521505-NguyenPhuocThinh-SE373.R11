---
name: refund-policy
description: Tra cứu và áp dụng chính sách hoàn tiền cho khách hàng dựa trên ngày mua hàng, ngày yêu cầu hoàn tiền và trạng thái kích hoạt sản phẩm. Dùng khi người dùng hỏi về quyền lợi hoàn tiền, tính hợp lệ của yêu cầu hoàn tiền, thời hạn hoàn tiền hoặc mức phí hoàn tiền.
---

# Refund policy

Hướng dẫn tra cứu và áp dụng chính sách hoàn tiền đúng phiên bản.

## 1. Kiểm tra thông tin đầu vào

Trước khi đưa ra kết luận hoàn tiền, bạn BẮT BUỘC phải có đủ 3 thông tin sau:
1. **Ngày mua hàng** (định dạng ngày cụ thể, ví dụ: 28/09/2026 hay 2026-09-28).
2. **Ngày yêu cầu hoàn tiền** (dùng ngày người dùng nêu trong câu hỏi, không dùng ngày hiện tại của máy tính).
3. **Trạng thái kích hoạt sản phẩm** (đã kích hoạt hay chưa kích hoạt).

> **QUY TẮC BẮT BUỘC**: Nếu người dùng thiếu bất kỳ thông tin nào trong 3 thông tin trên (đặc biệt là trạng thái kích hoạt sản phẩm), bạn **PHẢI HỎI LẠI** người dùng để bổ sung thông tin trước khi kết luận. Tuyệt đối **KHÔNG ĐƯỢC TỰ SUY DIỄN HOẶC GIẢ ĐỊNH** (ví dụ: không được tự giả định sản phẩm "chưa kích hoạt").

## 2. Tìm kiếm và đọc tài liệu chính sách

1. Dùng tool `list_files` để liệt kê thư mục `data/policies/`.
   - **Lưu ý**: Tên file có thể thay đổi (ví dụ do cập nhật hệ thống), do đó không được giả định tên file cố định mà phải dùng `list_files` để lấy danh sách file thực tế trong `data/policies/`.
2. Dùng tool `read_file` để đọc từng tài liệu chính sách tìm được trong `data/policies/`.
3. Xác định phạm vi ngày hiệu lực và các điều kiện của từng chính sách:
   - Phạm vi áp dụng theo ngày mua.
   - Thời hạn cho phép yêu cầu hoàn tiền (số ngày lịch kể từ ngày mua).
   - Mức phí hoàn tiền (nếu có).
   - Điều kiện về trạng thái kích hoạt (sản phẩm đã kích hoạt thì không hoàn tiền).

## 3. Chọn và áp dụng chính sách

1. **Chọn chính sách**: Căn cứ vào **ngày mua hàng** của khách hàng để đối chiếu với phạm vi hiệu lực của từng chính sách:
   - Ngày mua trước `2026-10-01`: Áp dụng chính sách trước tháng 10 (thời hạn 7 ngày, phí 10%, chưa kích hoạt).
   - Ngày mua từ `2026-10-01` (bao gồm ngày `2026-10-01`): Áp dụng chính sách từ tháng 10 (thời hạn 14 ngày, không thu phí, chưa kích hoạt).
2. **Tính số ngày đã qua**:
   - Số ngày = Chênh lệch ngày lịch giữa **ngày yêu cầu hoàn** và **ngày mua** (Ví dụ: từ 28/09/2026 đến 06/10/2026 là 8 ngày; từ 02/10/2026 đến 12/10/2026 là 10 ngày).
   - Nếu số ngày <= giới hạn của chính sách (bằng đúng giới hạn vẫn đủ điều kiện về thời gian) VÀ sản phẩm chưa kích hoạt -> **Đủ điều kiện hoàn tiền**.
   - Nếu số ngày > giới hạn của chính sách HOẶC sản phẩm đã kích hoạt -> **Không đủ điều kiện hoàn tiền**.

## 4. Cấu trúc câu trả lời

Đọc template tại `skills/refund-policy/references/answer-template.md` bằng `read_file` và trình bày câu trả lời theo đúng mẫu quy định, bao gồm:
1. **Chính sách áp dụng** (tên chính sách và phạm vi hiệu lực).
2. **Số ngày đã qua** (chênh lệch ngày lịch giữa ngày yêu cầu hoàn và ngày mua).
3. **Kết luận** (Đủ điều kiện hay Không đủ điều kiện hoàn tiền).
4. **Phí hoàn tiền** (nêu rõ mức phí nếu đủ điều kiện, hoặc không thu phí).
5. **Đường dẫn tài liệu làm căn cứ** (đường dẫn tương đối tới file chính sách trong `data/policies/`).
