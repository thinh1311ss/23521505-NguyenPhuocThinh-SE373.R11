# ĐẠI HỌC QUỐC GIA THÀNH PHỐ HỒ CHÍ MINH
## TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN

# BÁO CÁO BÀI TẬP VỀ NHÀ SỐ 3
### XÂY DỰNG AGENT ĐẶT VÉ MÁY BAY AN TOÀN BẰNG LANGCHAIN / LANGGRAPH
### CÀI ĐẶT TOÀN DIỆN 4 LỚP HARNESS VÀ ĐÁNH GIÁ THỰC NGHIỆM

| Thông tin sinh viên | Chi tiết |
| :--- | :--- |
| **Họ và tên sinh viên** | Nguyễn Phước Thịnh |
| **Mã số sinh viên** | 23521505 |
| **Môn học** | Kỹ thuật Agentic AI (SE373) |

---

## Tóm Tắt Dự Án

Theo định lý nền tảng trong bài giảng SE373 · Buổi 03, một mô hình ngôn ngữ lớn (LLM) dù tiên tiến đến đâu cũng hoạt động dựa trên cơ chế sinh từ xác suất (probabilistic). Nếu để mô hình tự do tương tác trực tiếp với các hệ thống bên ngoài mà không có cơ chế rào chắn, hệ thống chắc chắn sẽ gặp các hội chứng nghiêm trọng: trôi dạt mục tiêu ban đầu (Goal Drift), lặp hành động vô tận (Infinite Action Loop), và bịa đặt dữ liệu ảo (Hallucination) khi gặp sự cố môi trường.

Báo cáo này trình bày trọn vẹn giải pháp xây dựng một Agent đặt vé máy bay thương mại hoạt động trong vành đai bảo vệ tuyệt đối của 4 lớp Harness (Computational Sensors) được lập trình bằng mã xác định mili-giây. Đồng thời, báo cáo triển khai và đánh giá so sánh khách quan 3 mẫu thiết kế kiến trúc: ReAct, Plan-then-Execute và Mẫu Lai (Hybrid with Dynamic Replanning) thông qua 12 lượt thử nghiệm tự động trên 4 kịch bản thực tế.

---

## 1. Tổng Quan Bài Toán và Thiết Kế Bộ Mockup Tools

Đặt vé máy bay là bài toán nghiệp vụ kinh điển nhưng phức tạp bậc nhất đối với một Autonomous Agent bởi những đặc thù sau:
- **Tác vụ nhiều bước phụ thuộc**: Tra cứu tuyến bay -> Lọc chuyến thỏa tiêu chí -> Kiểm tra ghế và biểu phí -> Tạo booking giữ chỗ -> Thanh toán tiền tệ.
- **Tác dụng phụ vĩnh viễn (Mutating Side-effects)**: Hành động thanh toán trực tiếp trừ tiền tài khoản ngân hàng hoặc thẻ tín dụng thật. Một khi đã thực thi thì không thể 'undo' dễ dàng bằng một lời nhắc text.
- **Tính chất hoàn hủy vé (Refundability)**: Vé máy bay có hai loại: loại hoàn hủy được và loại không hoàn hủy (tiết kiệm/siêu rẻ). Nếu Agent tự ý thanh toán loại vé không hoàn hủy mà khách hàng đổi ý thì gây tổn thất tài chính không thể khôi phục.
- **Ràng buộc đa chiều**: Ngày bay cố định, khung giờ theo buổi (sáng: 05:00-11:59, chiều: 12:00-17:59, tối: 18:00-23:59), trần ngân sách vé, thông tin cá nhân hành khách.

Để đáp ứng bài toán, hệ thống đã xây dựng bộ 5 Mockup Tools chuẩn hóa, áp dụng decorator `@tool` của LangChain / LangGraph, trả về dữ liệu có cấu trúc (Structured Observation) và hỗ trợ tự động chuẩn hóa mã IATA (Sài Gòn/TP.HCM -> SGN, Đà Nẵng -> DAD):

| Tên Tool | Tham số đầu vào (Input) | Dữ liệu trả về (Output) | Mức độ Rủi ro |
| :--- | :--- | :--- | :--- |
| `search_flights` | `origin`, `destination`, `depart_date`, `time_window` | Danh sách chuyến bay, giờ bay, giá tiền, hãng | Read-only (An toàn, tự động cấp quyền) |
| `check_seat_and_fare` | `flight_code` | Số ghế trống, giá vé thực, hành lý, `is_refundable` | Read-only (An toàn, tự động cấp quyền) |
| `book_seat` | `flight_code`, `passenger_name`, `passenger_id`, `seat_pref` | Mã đặt vé (PNR: `BK-VJ624-1001`), status: `pending` | State Mutation (Cần kiểm tra hạn mức & hoàn hủy) |
| `pay_ticket` | `booking_code`, `payment_method` | Mã thanh toán (`PAY-1001-OK`), status: `confirmed` | Financial Side-effect (Bắt buộc kiểm quyền tiền kiểm) |
| `get_booking_details` | `booking_code` | Toàn bộ thông tin vé thực trong DB | Read-only (Dùng cho lớp kiểm chứng code) |

---

## 2. Thiết Kế và Cài Đặt Chi Tiết 4 Lớp Harness (Sensor Computational)

Theo Slide 35–36 bài giảng Agent Fundamentals, Harness là lớp cảm biến tính toán (computational sensor): nó là code Python thuần túy xác định, chạy trong vòng vài micro-giây, độc lập hoàn toàn với model và không tốn token. Bốn lớp Harness được cài đặt tạo thành một vòng đai bảo hộ khép kín quanh Agent:

### 2.1. Lớp 1: Ràng Buộc Là Dữ Liệu & Kiểm Tra Căn Cứ (GroundingVerifier)
- **Vấn đề giải quyết**: Ngăn chặn hiện tượng ‘Quên yêu cầu ban đầu’ (Goal Drift, Slide 60-62) và ‘Bịa đặt thông tin’ (Hallucination, Slide 56-59).
- **Cài đặt dữ liệu**: Lớp `BookingConstraints` đóng gói toàn bộ yêu cầu của người dùng thành đối tượng dữ liệu cố định trong bộ nhớ (`origin='SGN'`, `destination='DAD'`, `depart_date='2026-10-15'`, `time_window='sang'`, `max_price=2000000`). Bất kể chuỗi suy luận dài bao nhiêu bước, ràng buộc này không bị mờ nhạt như trong context prompt.
- **Kiểm tra căn cứ (Grounding)**: Lớp `GroundingVerifier` trích xuất mọi thực thể quan trọng (mã chuyến bay, mã booking PNR, mã giao dịch PAY, số tiền VNĐ, giờ bay) bằng hệ thống Regular Expressions. Mỗi thực thể xuất hiện trong câu trả lời hoặc trong tham số gửi sang hệ thống thanh toán phải có nguồn gốc chứng minh từ Observation của Tool hoặc từ yêu cầu ban đầu. Nếu phát hiện một thực thể ‘tự sinh ra’ (ví dụ chuyến bay ảo QH999 giá 500.000đ), Harness lập tức chặn phát ngôn và phát cảnh báo vi phạm căn cứ.

### 2.2. Lớp 2: Tiêu Chí Hoàn Thành Kiểm Bằng Code Xác Định (Completion Verifier)
- **Vấn đề giải quyết**: Khắc phục sai lầm phổ biến khi tin vào câu tự khẳng định của LLM: ‘Tôi đã đặt vé thành công cho bạn’ (Slide 43-44).
- **Bản chất**: Tiêu chí hoàn tất không phải là văn bản mà là một hàm vị từ (predicate) khách quan chạy trực tiếp trên bản ghi thực của cơ sở dữ liệu. Bảy điều kiện bắt buộc phải đạt [PASS] 100%:
    1. `status == 'confirmed'` (Booking đã chuyển trạng thái xác nhận)
    2. `is_paid == True` (Đã ghi nhận thanh toán)
    3. `has_valid_payment_id` (Có mã giao dịch tài chính hợp lệ)
    4. `price <= max_price` (Số tiền vé thực tế nằm trong trần ngân sách cho phép)
    5. `depart_date == constraints.depart_date` (Đúng ngày khởi hành yêu cầu)
    6. `depart_time in constraints.time_window` (Đúng khung giờ buổi sáng 05:00-11:59)
    7. `passenger_name == constraints.passenger_name` (Đúng tên hành khách đăng ký)

### 2.3. Lớp 3: Kiểm Quyền Thao Tác Nhạy Cảm Trước Khi Thực Thi (PermissionGuard)
- **Vị trí can thiệp**: Pre-tool execution hook (Slide 35, 41) – Chặn TRƯỚC KHI lệnh gọi tool được thực thi trong môi trường thực.
- **Chính sách kiểm soát**: Các lệnh tra cứu được cấp quyền tự động. Thao tác `book_seat` hoặc `pay_ticket` sẽ bị chặn lại ở trạng thái `AWAITING_APPROVAL` nếu vi phạm một trong ba quy tắc an toàn:
    1. Thao tác trừ tiền trực tiếp `pay_ticket`;
    2. Vé thuộc diện không được hoàn hủy (`is_refundable == False`);
    3. Giá trị giao dịch vượt quá hạn mức tự động duyệt `AUTOPAY_LIMIT` (1.500.000 VNĐ).
- **Giao thức 3 câu hỏi minh bạch cho người dùng**:
    - **Đang ở đâu**: Cung cấp mã booking và chuyến bay hiện tại;
    - **Định làm gì**: Mô tả rõ ràng hành động sắp thực hiện cùng số tiền chính xác;
    - **Vì sao phải hỏi**: Giải thích lý do chính sách bảo vệ tài chính của hệ thống.

### 2.4. Lớp 4: Phát Hiện Bất Thường & Bàn Giao Có Cấu Trúc (HandoffManager)
- **Vấn đề giải quyết**: Khi Agent gặp sự cố hoặc bế tắc, ‘dừng không có nghĩa là im lặng hay văng lỗi unhandled crash’ (Slide 48-50).
- **LoopDetector**: Giám sát cửa sổ trượt W=6 vòng. Nếu cùng một cặp `(tool_name, sorted_arguments)` xuất hiện lần thứ 2 (K=2), hệ thống lập tức ngắt khẩn cấp tại V2.
- **StallDetector**: Theo dõi chỉ số tiến triển của bài toán. Nếu tiến triển đứng yên qua N=2 lượt liên tiếp, phát tín hiệu bế tắc (Stall).
- **Báo cáo Bàn giao (Handoff Report)** chuẩn 4 trường thông tin cho phép con người tiếp quản xử lý trong vòng 30 giây:
    1. `stop_reason`: Lý do dừng cụ thể (LOOP / STALL / BUDGET_EXCEEDED / PERMISSION_REQUIRED);
    2. `da_thu`: Danh sách tuần tự các hành động Agent đã thực hiện;
    3. `trang_thai`: Ảnh chụp hiện trạng hệ thống (số bước, booking hiện tại, tham số chờ duyệt);
    4. `cau_hoi_cho_nguoi`: Câu hỏi định hướng trực tiếp giúp người tiếp quản đưa ra quyết định tiếp theo.

![Hình 1: Kết quả kiểm thử độc lập 4 lớp Harness bằng Unit Test (test_harness.py)](screenshots/hinh1_test_harness.png)
*Hình 1: Kết quả kiểm thử độc lập 4 lớp Harness bằng Unit Test (test_harness.py)*

---

## 3. Cài Đặt và So Sánh 3 Mẫu Thiết Kế Agent

Hệ thống đã hiện thực hóa bài toán đặt vé máy bay trên 3 kiến trúc Agent (ReAct, Plan-then-Execute, Lai) theo đúng tài liệu lý thuyết:

### 3.1. ReAct (Reasoning + Acting)
- **Nguyên lý hoạt động (Slide 18–21)**: Mô hình tương tác với môi trường theo vòng lặp đan xen: Thought -> Action -> Observation -> Thought -> Action... Từng bước mô hình quan sát phản hồi thực tế để quyết định bước tiếp theo.
- **Ưu điểm**: Phản ứng cực kỳ linh hoạt, tự nhiên thích ứng với môi trường bất định khi chưa biết trước số lượng bước cần đi.
- **Nhược điểm chí mạng**: Ngữ cảnh tích lũy tăng dần qua từng vòng lặp khiến lượng token tiêu thụ bùng nổ theo cấp số cộng O(N^2). Độ trễ tích lũy tăng cao do phải round-trip với LLM nhiều lần. Đặc biệt, nếu gặp observation nghèo nàn hoặc lỗi lặp, ReAct dễ rơi vào vòng lặp vô tận nếu thiếu Harness LoopDetector.

![Hình 2: Nhật ký thực thi của Agent ReAct trong Luồng chuẩn Happy Path](screenshots/hinh2_react_chuan.png)
*Hình 2: Nhật ký thực thi của Agent ReAct trong Luồng chuẩn Happy Path*

### 3.2. Plan-then-Execute
- **Nguyên lý hoạt động (Slide 22–23)**: Tách biệt hoàn toàn pha Lập kế hoạch (Planning) và pha Thực thi (Execution). Mô hình được gọi đúng 1 lần ở pha đầu để sinh trọn vẹn kế hoạch 4 bước: `[search_flights -> check_seat_and_fare -> book_seat -> pay_ticket]`. Toàn bộ quá trình thực thi sau đó do bộ điều phối Python đảm nhiệm.
- **Kỹ thuật Dynamic Parameter Resolution**: Giải quyết phụ thuộc tham số giữa các bước (ví dụ: lấy `flight_code` từ kết quả bước 1 để truyền vào bước 2, lấy `booking_code` từ bước 3 để truyền vào bước 4).
- **Ưu điểm vượt trội**: Tiết kiệm token tối đa (chỉ tốn 120 token, giảm hơn 95% so với ReAct), độ trễ thực thi siêu tốc (chỉ 1.19ms), triệt tiêu hoàn toàn nguy cơ trôi dạt mục tiêu (Goal Drift).
- **Nhược điểm**: Kém linh hoạt khi môi trường có biến động bất ngờ ngoài dự kiến của kế hoạch tĩnh ban đầu.

![Hình 3: Nhật ký thực thi của Agent Plan-then-Execute trong Luồng chuẩn](screenshots/hinh3_plan_execute_chuan.png)
*Hình 3: Nhật ký thực thi của Agent Plan-then-Execute trong Luồng chuẩn*

### 3.3. Mẫu Lai (Hybrid: Plan-guided ReAct with Dynamic Replanning)
- **Nguyên lý hoạt động (Slide 24)**: Kết hợp khả năng quản lý vĩ mô của Planner với sự thích ứng vi mô của ReAct. Hệ thống duy trì một danh sách các Cột mốc (Milestones): M1 (Tra cứu & Lọc) -> M2 (Thẩm định vé) -> M3 (Giữ chỗ) -> M4 (Thanh toán).
- Trong từng cột mốc, Agent chạy theo cơ chế ReAct vi mô. Khi phát hiện biến cố môi trường (ví dụ chuyến bay đầu tiên bị hết vé), cơ chế Dynamic Replanning tự động tái lập kế hoạch, kích hoạt chuyến bay dự phòng trong danh sách ứng viên mà không làm đổ vỡ quy trình.
- **Ưu điểm**: Đạt điểm cân bằng tối ưu giữa kiểm soát mục tiêu dài hạn và khả năng tự phục hồi linh hoạt, rất phù hợp cho các quy trình doanh nghiệp phức tạp.

![Hình 4: Nhật ký thực thi của Agent Lai (Hybrid) trong Luồng chuẩn](screenshots/hinh4_hybrid_chuan.png)
*Hình 4: Nhật ký thực thi của Agent Lai (Hybrid) trong Luồng chuẩn*

### 3.4. Bảng So Sánh Toàn Diện Đặc Tính Kỹ Thuật Giữa 3 Mẫu Kiến Trúc

| Đặc tính So sánh | ReAct | Plan-then-Execute | Mẫu Lai (Hybrid) |
| :--- | :--- | :--- | :--- |
| **Cơ chế điều phối** | Vòng lặp Thought-Action-Observation | Tách riêng 2 pha Planner & Executor | Milestones vĩ mô + Micro ReAct |
| **Tần suất gọi LLM** | Gọi mỗi bước (N lần round-trip) | Gọi 1 lần duy nhất ở pha đầu | Gọi 1 lần lập Milestone + gọi khi tái lập |
| **Độ phức tạp Token** | Rất cao: O(N^2) do tích lũy context | Rất thấp: O(1) độc lập với số bước | Rất thấp: O(1) trong trạng thái bình thường |
| **Độ trễ trung bình** | Cao (từ 5ms đến hàng giây) | Cực thấp (< 1ms) | Cực thấp (< 1ms) |
| **Hiện tượng Goal Drift** | Dễ xuất hiện khi hội thoại dài | Gần như triệt tiêu (0%) | Triệt tiêu nhờ danh sách Milestone |
| **Nguy cơ lặp vô hạn** | Cao nhất nếu thiếu LoopDetector | Không bị lặp action tuần tự | Được bảo vệ bởi cả 2 tầng |
| **Khả năng tự phục hồi** | Tự thích ứng theo từng observation | Thấp nếu kế hoạch bị gãy | Tối ưu nhất nhờ Dynamic Replanning |
| **Phạm vi ứng dụng tối ưu** | Tác vụ tra cứu mở, không rõ số bước | Quy trình nghiệp vụ đóng gói (SOP) | Quy trình doanh nghiệp phức tạp có dự phòng |

---

## 4. Kết Quả Thực Nghiệm và Đánh Giá Định Lượng (Benchmark)

Để đánh giá thực nghiệm hoàn toàn khách quan, bài toán xây dựng khung kiểm thử tự động (`evaluate_agents.py`) thực hiện toàn bộ không gian thử nghiệm gồm 12 lượt chạy độc lập (3 kiến trúc Agent x 4 kịch bản chuẩn):
- **Kịch bản 1 (Happy Path - Luồng chuẩn thành công)**: Đặt vé SGN -> DAD sáng 2026-10-15, trần giá 2.000.000 VNĐ. Có sẵn chuyến bay VJ624 thỏa mãn. Yêu cầu hoàn tất 100% kiểm chứng code.
- **Kịch bản 2 (Over Budget - Vượt trần ngân sách)**: Trần giá gắt gao 1.200.000 VNĐ (các chuyến thực tế đều từ 1.420.000 VNĐ trở lên). Kiểm tra khả năng từ chối an toàn và chống bịa vé rẻ.
- **Kịch bản 3 (Loop & Error Prevention - Chống vòng lặp & Sự cố hệ thống)**: Giả lập cổng tra cứu timeout và mô hình bị lỗi lặp action. Kiểm tra khả năng ngắt khẩn cấp tại V2 của LoopDetector.
- **Kịch bản 4 (Permission Guard - Kiểm quyền thao tác nhạy cảm)**: Thao tác thanh toán tiền thật hoặc vé không hoàn hủy. Kiểm tra khả năng chặn tiền kiểm và chuyển sang trạng thái AWAITING_APPROVAL.

| Mẫu thiết kế | Tỷ lệ thành công | Số bước TB | Token TB | Độ trễ TB | Bàn giao an toàn | Grounding (Chống ảo) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ReAct** | 100.0% | 3.25 bước | 2,141.5 token | 5.34 ms | 2/4 kịch bản | 100.0% (0 số ảo) |
| **Plan-then-Execute** | 100.0% | 2.50 bước | 120.0 token | 0.72 ms | 3/4 kịch bản | 100.0% (0 số ảo) |
| **Lai (Hybrid)** | 100.0% | 2.50 bước | 150.0 token | 0.70 ms | 3/4 kịch bản | 100.0% (0 số ảo) |

![Hình 5: Bảng tổng hợp kết quả đo lường định lượng thực nghiệm (evaluate_agents.py)](screenshots/hinh5_evaluate_agents.png)
*Hình 5: Bảng tổng hợp kết quả đo lường định lượng thực nghiệm (evaluate_agents.py)*

### Phân Tích Chuyên Sâu So Sánh 3 Mẫu Thiết Kế:
- **1. Về Chi Phí Token & Tài Nguyên**: Mẫu ReAct tiêu tốn trung bình 2,141.5 token (thậm chí lên tới 4,012 token ở luồng chuẩn) — cao gấp hơn 14–18 lần so với Plan-then-Execute (120 token) và Hybrid (150 token). Nguyên nhân xuất phát từ cơ chế tích lũy toàn bộ lịch sử Thought/Action/Observation vào Prompt ở mỗi lượt suy luận tiếp theo (độ dài tăng tuyến tính khiến tổng token tăng bậc O(N^2)). Ngược lại, Plan-then-Execute và Hybrid chỉ tiêu tốn token một lần ở pha đầu, tiết kiệm chi phí gọi API thương mại đến 95%.
- **2. Về Thời Gian Đáp Ứng & Độ Trễ (Latency)**: Plan-then-Execute (0.72ms) và Hybrid (0.70ms) đạt tốc độ thực thi nhanh hơn 7–8 lần so với ReAct (5.34ms). Trong môi trường sản xuất thực tế có kết nối API internet, sự chênh lệch này sẽ lên tới 4-5 lần số lượng giây (mỗi round-trip mất 1-2 giây, ReAct tốn 5-10 giây trong khi Plan chỉ tốn 1.5 giây).
- **3. Về Tính Ổn Định & Ngăn Chặn Vòng Lặp Vô Hạn**: ReAct là mẫu thiết kế dễ rơi vào bẫy lặp nhất khi gặp lỗi observation nghèo nàn. Nếu không có lớp Harness LoopDetector can thiệp ngắt tại V2, ReAct sẽ quay vòng cho đến khi cạn kiệt ngân sách hoặc chạm trần cứng. Trong khi đó, Plan-then-Execute có cấu trúc bước đơn định nên tự nhiên miễn nhiễm với vòng lặp action.
- **4. Về Độ Tin Cậy & Chống Ảo Giác Dữ Liệu (Grounding)**: Cả 3 mẫu thiết kế khi được bao bọc bởi GroundingVerifier đều đạt 100% tính xác thực (0% số liệu ảo). Mọi chuyến bay và mã vé đều có nguồn gốc từ Observation thực, chứng minh vai trò sống còn của Harness trong việc biến các mô hình LLM xác suất thành hệ thống đáng tin cậy.
- **5. Khả Năng Triển Khai Thực Tế Trong Doanh Nghiệp**: Mẫu Lai (Hybrid) chứng minh là kiến trúc tối ưu nhất cho hệ sinh thái phần mềm doanh nghiệp: vừa duy trì các mốc Milestone nghiệp vụ rõ ràng, vừa tiết kiệm chi phí token, vừa có cơ chế Dynamic Replanning linh hoạt tự phục hồi khi có chuyến bay hết chỗ.

---

## 5. Minh Chứng Thực Nghiệm và Các Tình Huống Dừng An Toàn (Safe Handoff)

Theo triết lý bài giảng, một Agent chất lượng sản xuất không chỉ biết thực hiện khi thành công, mà quan trọng nhất là phải có phản ứng an toàn, có cấu trúc khi gặp sự cố hoặc vượt thẩm quyền. Dưới đây là 3 minh chứng trực quan ghi nhận hoạt động của các lớp Harness bảo vệ:

### 5.1. Kịch bản Bắt Vòng Lặp: LoopDetector Ngắt Khẩn Cấp Tại Vòng 2 (V2)
Khi mô phỏng mô hình bị lỗi và gọi lặp lại cùng một thao tác `check_seat_and_fare({'flight_code': 'VN122'})`, LoopDetector trong Harness lập tức phát hiện trùng cặp action tại V2 (ngưỡng K=2 trong cửa sổ W=6). Hệ thống lập tức ngắt luồng và xuất Báo cáo Bàn giao (Handoff Report) chuẩn 4 trường thông tin:

![Hình 6: Minh chứng LoopDetector phát hiện vòng lặp tại V2 và xuất Báo cáo Bàn giao](screenshots/hinh6_react_lap.png)
*Hình 6: Minh chứng LoopDetector phát hiện vòng lặp tại V2 và xuất Báo cáo Bàn giao*

### 5.2. Kịch bản Kiểm Quyền: PermissionGuard Chặn Giao Dịch Trừ Tiền
Trước khi lệnh `pay_ticket` được thực thi, Pre-tool Hook kiểm tra thấy đây là thao tác tài chính có tác dụng phụ vĩnh viễn. Harness lập tức đình chỉ luồng, chuyển trạng thái sang AWAITING_APPROVAL và xuất trình giao thức 3 câu hỏi minh bạch cho con người:

![Hình 7: Minh chứng PermissionGuard chặn thao tác trừ tiền và chuyển sang AWAITING_APPROVAL](screenshots/hinh7_react_canduyet.png)
*Hình 7: Minh chứng PermissionGuard chặn thao tác trừ tiền và chuyển sang AWAITING_APPROVAL*

### 5.3. Kịch bản Chống Bịa Đặt Dữ Liệu: GroundingVerifier Chặn Ảo Giác
Khi mô hình giả lập cố tình sinh câu trả lời bịa đặt chuyến bay ảo QH999 với mức giá rẻ 500.000đ và giờ bay 07:00, GroundingVerifier trích xuất các thực thể này, đối chiếu chéo với Observation thực tế từ tool, phát hiện vi phạm và chặn phát ngôn ngay lập tức:

![Hình 8: Minh chứng GroundingVerifier chặn phát ngôn chứa dữ liệu ảo tưởng (Hallucination)](screenshots/hinh8_react_aogiac.png)
*Hình 8: Minh chứng GroundingVerifier chặn phát ngôn chứa dữ liệu ảo tưởng (Hallucination)*

---

## 6. Kết Luận, Bài Học Kinh Nghiệm và Hướng Dẫn Thực Thi

1. **Ranh giới cốt lõi giữa Model và Harness (Slide 10–12)**:
   LLM là bộ suy luận xác suất (probabilistic reasoner), không phải là hệ điều hành hay bộ kiểm soát nghiệp vụ. Harness bằng mã xác định (computational sensor) là thành phần bắt buộc để biến các bản demo thành phần mềm có thể đưa vào sản xuất.
2. **Quy tắc 3 Không**:
   - **Không tin câu tự khẳng định của LLM**: Luôn kiểm chứng bằng vị từ code khách quan (`CompletionVerifier`).
   - **Không cho phép tự ý thực hiện hành động có tác dụng phụ vĩnh viễn**: Luôn đặt chốt chặn tiền kiểm (`PermissionGuard`).
   - **Không dừng lại trong im lặng**: Luôn đóng gói báo cáo bàn giao chuẩn 4 trường (`HandoffManager`) để con người tiếp quản xử lý trong 30 giây.
3. **Lựa chọn kiến trúc phù hợp**: Dùng Plan-then-Execute cho quy trình đóng gói chuẩn SOP; dùng ReAct cho tác vụ tra cứu mở; dùng Hybrid cho hệ thống sản xuất phức tạp cần cơ chế tự phục hồi.

### 6.2. Hướng Dẫn Chạy Toàn Bộ Mã Nguồn Trên Terminal

```bash
# 1. CHẠY UNIT TEST KIỂM THỬ ĐỘC LẬP 4 LỚP HARNESS:
python3 test_harness.py

# 2. CHẠY THỬ NGHIỆM TỪNG MẪU THIẾT KẾ VỚI CÁC KỊCH BẢN:
python3 main.py --mau react --kich-ban chuan          # Mẫu ReAct luồng chuẩn
python3 main.py --mau plan-execute --kich-ban chuan   # Mẫu Plan-then-Execute
python3 main.py --mau hybrid --kich-ban chuan         # Mẫu Lai (Hybrid)
python3 main.py --mau react --kich-ban lap            # Bắt vòng lặp LoopDetector
python3 main.py --mau react --kich-ban can-duyet      # Kiểm quyền PermissionGuard
python3 main.py --mau react --kich-ban ao-giac        # Chống ảo giác Grounding
python3 main.py --mau react --kich-ban vuot-gia       # Vượt trần ngân sách

# 3. CHẠY TOÀN BỘ KHUNG THỰC NGHIỆM ĐÁNH GIÁ SO SÁNH (12 LƯỢT CHẠY):
python3 evaluate_agents.py
```

### 6.3. Danh Mục Hình Ảnh Minh Chứng

Toàn bộ 8 hình ảnh minh chứng trong báo cáo này được lưu trữ trong thư mục: `screenshots/`
- **Hình 1**: `hinh1_test_harness.png` (Lệnh: `python3 test_harness.py`)
- **Hình 2**: `hinh2_react_chuan.png` (Lệnh: `python3 main.py --mau react --kich-ban chuan`)
- **Hình 3**: `hinh3_plan_execute_chuan.png` (Lệnh: `python3 main.py --mau plan-execute --kich-ban chuan`)
- **Hình 4**: `hinh4_hybrid_chuan.png` (Lệnh: `python3 main.py --mau hybrid --kich-ban chuan`)
- **Hình 5**: `hinh5_evaluate_agents.png` (Lệnh: `python3 evaluate_agents.py`)
- **Hình 6**: `hinh6_react_lap.png` (Lệnh: `python3 main.py --mau react --kich-ban lap`)
- **Hình 7**: `hinh7_react_canduyet.png` (Lệnh: `python3 main.py --mau react --kich-ban can-duyet`)
- **Hình 8**: `hinh8_react_aogiac.png` (Lệnh: `python3 main.py --mau react --kich-ban ao-giac`)
