# Kế hoạch triển khai — Mercari JP New-Listing Alert Bot

Phiên bản 1.0 | 09/09/2026

---

## 1. Đánh giá tính khả thi

### 1.1 Kết luận

**Khả thi.** Không có hạng mục nào bất khả thi về kỹ thuật. Nhưng ~80% rủi ro
của dự án nằm ở đúng một chỗ: lấy được dữ liệu listing theo thứ tự thời gian từ
Mercari mà không đăng nhập.

### 1.2 Phân rã rủi ro theo hạng mục

| Hạng mục | Độ khó | Rủi ro | Ghi chú |
|---|---|---|---|
| Telegram notification | Thấp | Rất thấp | Bot API ổn định, có sẵn `sendMediaGroup` |
| SQLite dedup + persistence | Thấp | Rất thấp | Bài toán kinh điển |
| Keyword config YAML | Thấp | Rất thấp | |
| Scheduler + auto-restart | Thấp | Rất thấp | Docker `restart: always` |
| Đóng gói + deploy VPS | Thấp | Thấp | |
| **Lấy dữ liệu Mercari** | **Trung bình** | **Cao** | Điểm chết của dự án |
| Vận hành dài hạn | — | Trung bình–cao | Mercari đổi API bất cứ lúc nào |

### 1.3 Những gì đã xác minh được về nguồn dữ liệu

- `jp.mercari.com` là SPA Next.js, kết quả tìm kiếm render phía client. Không
  parse được bằng HTML tĩnh.
- Endpoint nội bộ: `POST https://api.mercari.jp/v2/entities:search`. Nó yêu cầu
  header `DPoP` theo RFC 9449, ký bằng ECDSA P-256 (ES256). Khoá được sinh phía
  client — **không cần tài khoản, không cần cookie, không cần login**.
- Nhiều công cụ đang chạy production hiện nay ký DPoP thuần HTTP thành công, tức
  là đường HTTP-only vẫn khả dụng, không bắt buộc phải chạy trình duyệt.
- API hỗ trợ sort **Newest** (`SORT_CREATED_TIME` + `ORDER_DESC`) → trả lời được
  câu hỏi spike quan trọng nhất: có ép được thứ tự mới-nhất-trước, không phải
  thứ tự gợi ý.
- Response search đã có sẵn: `id`, `name`, `price`, `status`, `condition`,
  `brand`, `sellerId`, `thumbnail`, `itemUrl`, `created`, `updated`.
  → **Toàn bộ trường bắt buộc ở §2.3 của spec đã đủ từ search**. Chỉ riêng yêu
  cầu 1–4 ảnh mới cần gọi thêm trang chi tiết, và chỉ gọi khi đã phát hiện item
  mới thật sự — đúng như spec dự đoán.

### 1.4 Rủi ro thật sự cần chuẩn bị

**a) IP / ASN.** Mercari lọc IP theo mức tin cậy và nhận diện dải datacenter. Có
báo cáo dải của các nhà cung cấp cloud lớn bị chặn. IP ngoài Nhật có thể bị từ chối.

→ Quyết định hạ tầng phải chốt **trước khi code**: dùng VPS đặt tại Nhật
(Sakura, ConoHa, Xserver, Vultr Tokyo, Linode Tokyo). Đây là biến số quan trọng
hơn cả framework. Chạy spike từ chính VPS định dùng, không chỉ từ máy local ở
Hà Nội.

**b) Chi phí — loại bỏ sớm phương án API bên thứ ba.** Các scraper thương mại
tính ~$1.5–4 / 1.000 kết quả. Với 10 keyword, poll mỗi 90 giây, 30 item mỗi lần:

```
10 keyword × 960 chu kỳ/ngày × 30 item = 288.000 kết quả/ngày
288.000 × $0.002 ≈ $576/ngày ≈ $17.000/tháng
```

→ Không dùng được cho monitoring liên tục. Chỉ hợp lý cho nghiên cứu one-off.
Phương án tự host là phương án duy nhất khả thi về kinh tế.

**c) Nợ bảo trì.** Đây là API nội bộ không có cam kết. Kiến trúc phải giả định
nó sẽ hỏng. Đó là lý do `ListingSource` là Strategy, và tại sao "0 kết quả toàn
bộ keyword" phải kêu báo động chứ không im lặng.

**d) Điều khoản sử dụng.** ToS của Mercari nhìn chung cấm truy cập tự động.
Việc đọc dữ liệu công khai, tần suất thấp, phục vụ mục đích cá nhân là vùng xám;
hậu quả thực tế thường là chặn IP chứ không phải chuyện pháp lý. Tôi không phải
luật sư — bạn nên tự đọc ToS và tự quyết định mức rủi ro chấp nhận được. Các
guardrail trong spec (không login, không bypass CAPTCHA, không mua tự động) đã
đặt đúng chỗ và cần giữ nguyên.

### 1.5 Bài toán latency — tính cụ thể

Mục tiêu spec: 1–3 phút.

| Cấu hình | Chu kỳ đầy đủ | Latency p50 | Latency p95 | Request/ngày |
|---|---|---|---|---|
| Aggressive: gap 6s | ~60s | ~30s | ~65s | 14.400 |
| **Khuyến nghị: gap 12s** | **~120s** | **~60s** | **~125s** | **7.200** |
| Bảo thủ: gap 18s | ~180s | ~90s | ~185s | 4.800 |

Cộng thêm 1 request chi tiết (~1s) và Telegram (~1–2s). Cấu hình khuyến nghị cho
end-to-end khoảng 60–130 giây → **đạt mục tiêu 1–3 phút với biên an toàn**.

Chiến lược: khởi động ở mức bảo thủ (gap 18s), soak 48 giờ, chỉ siết xuống 12s
nếu error rate = 0. Đừng bắt đầu ở mức aggressive.

---

## 2. Ước lượng thời gian

Bản này đã tính cả UI settings, vốn nằm ngoài scope spec gốc (§6.2).

| Phạm vi | Giờ công | Tới lúc deploy | Tới lúc nghiệm thu xong |
|---|---|---|---|
| Có UI (34 task) | 65–80 | 8 ngày | 10 ngày |
| Không UI (bỏ Wave 10, 11) | 48–58 | 6 ngày | 8 ngày |

Soak 48 giờ là ràng buộc cứng, không nén được.

Chạy song song nhiều session rút ngắn được các Wave rộng, nhưng **không** rút
ngắn đường găng, và review của con người thì tuần tự. Ba session là điểm hợp
lý; nhiều hơn thì bạn thành nút cổ chai.

Chi tiết từng task, phụ thuộc, tên branch và nhóm chạy song song: `docs/TASKS.md`.
Quy trình và vòng lặp review: `docs/WORKFLOW.md`.

---

## 3. Chi phí vận hành ước tính

| Khoản | Tháng |
|---|---|
| VPS Nhật (1 vCPU, 1–2GB) | $5–12 |
| Telegram Bot API | $0 |
| Proxy JP (chỉ khi spike fail) | $15–50 |
| **Tổng dự kiến** | **$5–12**, xấu nhất $60 |
