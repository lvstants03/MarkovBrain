# MarkovLotto - Hệ Thống Thu Thập & Dự Đoán Xổ Số Siêu Tốc 5 Phút (pmb5p) - CÔNG CỤ HỖ TRỢ NGHIÊN CỨU HỌC THUẬT - CHÚNG TÔI KHÔNG CÓ TRÁCH NHIỆM CHO NHỮNG HÀNH VI LỢI DỤNG VÀ CHIẾM ĐOẠT CỦA BẠN.

`MarkovLotto` là một công cụ pair-programming giúp cào dữ liệu thời gian thực từ WebSocket của trang game chính `vip.ee8833.me` / `ee8822.me` đối với loại hình **Xổ Số Miền Bắc Siêu Tốc 5 Phút (pmb5p)** và áp dụng thuật toán **Xích Markov cấp 1** để phân tích xác suất, chuỗi bệt, từ đó đưa ra dự đoán kết quả (Tài/Xỉu, Chẵn/Lẻ) cho kỳ kế tiếp.

---

## 🛠️ Công Nghệ Sử Dụng

-   **Backend:** Python 3.10+, FastAPI (Tạo API và tài liệu Swagger UI tự động)
-   **Web Server:** Uvicorn
-   **Giao Thức:** WebSockets (Kết nối thời gian thực nhận kết quả)
-   **Tính Toán:** Pandas & Numpy (Xử lý chuỗi số và tính toán ma trận chuyển trạng thái Markov)

---

## 🚀 Hướng Dẫn Cài Đặt & Khởi Chạy

### 1. Cài đặt thư viện yêu cầu:
Mở Terminal tại thư mục dự án và chạy lệnh:
```bash
pip install -r requirements.txt
```

### 2. Khởi chạy Server:
Để chạy server cục bộ, bạn chạy lệnh sau (chạy từ thư mục cha của `src`):
```bash
$env:PYTHONPATH=".."; python -m uvicorn main:app --reload --port 8000
```
Sau khi chạy, giao diện tương tác Swagger UI sẽ khả dụng tại: **`http://localhost:8000/docs`**

---

## 🔄 Quy Trình Vận Hành Thời Gian Thực

Do cơ chế bảo mật chữ ký động và mã hóa RSA của trang chính, hệ thống hoạt động thông qua cơ chế lắng nghe WebSocket trực tiếp bằng Token được cấp từ trình duyệt đã đăng nhập.

### Bước 1: Cập nhật Token mới (Sau khi mở máy hoặc Token hết hạn)
1. Đăng nhập tài khoản của bạn tại trang `https://vip.ee8833.me` (hoặc domain phụ tương tự).
2. Nhấn **F12** -> chọn tab **Network** (Mạng) -> chọn bộ lọc **WS** (WebSockets).
3. Tải lại trang (F5) và chọn kết nối có tên `/ws/`.
4. Sao chép toàn bộ giá trị của tham số `token=...` trong URL của kết nối đó.
5. Truy cập Swagger UI `http://localhost:8000/docs`, tìm đến API **`POST /api/config-token`**, bấm *Try it out*, dán mã token vừa sao chép vào rồi bấm **Execute**.

### Bước 2: Nạp nhanh lịch sử để tăng độ chính xác của dự đoán
Do server lưu dữ liệu trong bộ nhớ tạm thời (RAM), lúc mới khởi động sẽ chưa có đủ số lượng kỳ quay để thuật toán dự đoán chính xác (Yêu cầu tối thiểu 10 kỳ, khuyên dùng trên 50 kỳ):
1. Trong tab **Network** (F12) trên trình duyệt, tìm request tên là `drawResult?lottery_id=45...`.
2. Click vào request đó -> chọn tab **Response** (Phản hồi) ở khung bên cạnh -> Copy toàn bộ chuỗi JSON hiển thị trong đó.
3. Trên Swagger UI, tìm API **`POST /api/import-history`**, chọn *Try it out*, dán chuỗi JSON vừa copy vào ô body rồi bấm **Execute**.

### Bước 3: Xem kết quả dự đoán kỳ tiếp theo
1. Gọi API **`GET /api/statistics`** trên Swagger UI.
2. Dữ liệu trả về sẽ hiển thị đầy đủ thông tin:
    -   `probabilities`: Tỉ lệ xuất hiện thực tế (Chẵn, Lẻ, Tài, Xỉu).
    -   `streaks`: Số kỳ đang bệt liên tiếp của trạng thái hiện tại.
    -   `prediction_for_next_issue`: Xác suất phần trăm dự đoán cho kỳ quay tiếp theo dựa trên Markov Chain cấp 1.

---

---

## 🧠 Chức Năng, Logics & Khả Năng Tính Toán

### 1. Các chức năng chính của mã nguồn hiện tại
* **WebSocket Scraper**: Lắng nghe và cào dữ liệu xổ số thời gian thực từ trang chủ game chính thức (`vip.ee8833.me` / `ee8822.me`).
* **HTTP Automated Fetcher**: Tự động gửi các yêu cầu đồng bộ để lấy dữ liệu lịch sử xổ số định kỳ, hỗ trợ cập nhật dữ liệu tự động.
* **FastAPI Web Server**: Cung cấp tài liệu Swagger UI tự động để dễ dàng thao tác cấu hình Token, nạp lịch sử hoặc xuất kết quả phân tích.
* **In-Memory Storage (RAM)**: Lưu trữ lịch sử kỳ quay tạm thời trên RAM để tối ưu hóa tốc độ truy xuất và tính toán thời gian thực.

### 2. Logics tính toán
* **Xác suất phân bổ thực tế**: Phân tích tần suất và tỉ lệ phần trăm xuất hiện thực tế của các cửa Chẵn/Lẻ, Tài/Xỉu trên tổng số kỳ quay đã thu thập.
* **Thống kê bệt (Streaks Transitions)**: Xác định chuỗi bệt hiện tại đang kéo dài bao nhiêu kỳ. Đồng thời tìm kiếm trong lịch sử các chuỗi bệt có cùng độ dài để thống kê tỉ lệ tiếp tục bệt hoặc gãy chuỗi (chuyển trạng thái).
* **Xích Markov cấp 1 (Markov Chain)**: Xây dựng ma trận chuyển trạng thái giữa các kỳ quay liền kề trong lịch sử để dự đoán xác suất xuất hiện của cửa tiếp theo.

### 3. Khả năng tính toán (Điều kiện tính toán)
* **Yêu cầu dữ liệu tối thiểu cho Markov Chain**: Thuật toán dự đoán Xích Markov cấp 1 yêu cầu dữ liệu lịch sử tối thiểu **10 kỳ**. Nếu số kỳ quay trong RAM nhỏ hơn hoặc bằng 10, hệ thống sẽ từ chối giả lập dự đoán và báo kết quả dự báo là `"Không có"`.
* **Yêu cầu mẫu đối chứng cho bệt (Streaks)**: Để đưa ra dự đoán chuỗi bệt có độ tin cậy cao, hệ thống yêu cầu tối thiểu **3 mẫu lịch sử cùng độ dài bệt** (`MIN_SAMPLES = 3`) và xác suất gãy/tiếp tục bệt phải lớn hơn hoặc bằng **90%** (`CONFIDENCE_THRESHOLD = 0.90`). Nếu không thỏa mãn hai điều kiện này, dự đoán chuỗi bệt sẽ báo kết quả là `"Không có"`.

---

## 📡 Danh Sách API Endpoints

| Phương thức | Đường dẫn (Endpoint) | Chức năng |
| :--- | :--- | :--- |
| **GET** | `/api/history` | Lấy danh sách lịch sử kỳ quay đã lưu trong RAM |
| **GET** | `/api/statistics` | Xem thống kê xác suất & kết quả dự đoán kỳ tiếp theo |
| **POST** | `/api/config-token` | Cập nhật động token và tự động kết nối lại WebSocket |
| **POST** | `/api/import-history` | Import nhanh dữ liệu lịch sử copy từ Network tab trình duyệt |
| **POST** | `/api/clear` | Xóa sạch lịch sử hiện tại trong bộ lưu trữ |

---

## ⚠️ Lưu Ý Quan Trọng

1.  **Không giả lập dữ liệu**: Chế độ giả lập tự động phát sinh dữ liệu khi mất kết nối đã được tắt hoàn toàn theo yêu cầu hệ thống. Nếu không có dữ liệu thật hoặc token hết hạn, hệ thống sẽ báo `"Không có"` kết quả tính toán.
2.  **Lưu trữ tạm thời**: Dữ liệu được lưu trực tiếp trên RAM để tối ưu tốc độ đọc ghi tính toán nhanh. Khi tắt server, dữ liệu sẽ bị xóa. Bạn chỉ cần thực hiện lại Bước 2 khi khởi chạy lại server để nạp lại lịch sử.
