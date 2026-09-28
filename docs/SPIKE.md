# Technical Spike Report

Điền file này trước khi viết bất kỳ dòng code sản phẩm nào. Đây là cổng chặn.

Ngày chạy: 2026-09-28 | Keyword thử: `OMEGA 168.005`

Script: `spike/probe_mercari.py`, 50 chu kỳ, gap 60 giây, tuần tự, không retry.
Lệnh: `probe_mercari.py --keyword "OMEGA 168.005" --cycles 50 --gap-seconds 60`.

Lần chạy bổ sung trên VPS với keyword rộng `OMEGA`, 30 chu kỳ, gap 60 giây, để
quan sát item mới xuất hiện thật: 30/30 HTTP 200, p50 0,087 s, p95 0,118 s,
0 lỗi. Mỗi request trả 29 item thay vì 30.

---

## 1. Hai môi trường, chạy cùng một script

| | Local (Hà Nội) | VPS Nhật (VPS Siêu Tốc 1 GB) |
|---|---|---|
| IP / ASN | IP nhà mạng Việt Nam, ASN chưa ghi | JP, AS22439 Perfect International, Inc |
| Kết quả tổng | ☒ Pass ☐ Fail | ☒ Pass ☐ Fail |
| Tỉ lệ thành công | 98,0% (49/50) | 100,0% (50/50) |
| Latency p50 | 0,246 s | 0,103 s |
| Latency p95 | 0,294 s | 0,157 s |
| HTTP 200 | 49 | 50 |
| HTTP 403 | 0 | 0 |
| HTTP 429 | 0 | 0 |
| Timeout | 0 | 0 |
| Lỗi parse | 0 | 0 |

Lỗi duy nhất ở local là `transport_error` ở chu kỳ 18 (0,004 s, chưa hề tới
Mercari): máy local vừa thức dậy sau sleep, đồng hồ nhảy từ 04:13 sang 14:54
UTC. Đó là lỗi mạng local, không phải Mercari từ chối.

## 2. Câu hỏi bắt buộc trả lời

| # | Câu hỏi | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Truy cập được search không cần đăng nhập? | Có | 99/100 request trả 200 với 30 item, chỉ DPoP proof ES256 sinh key mới, không cookie, không token |
| 2 | Ép được thứ tự mới-nhất-trước thật sự? | **Không** | `SORT_CREATED_TIME` + `ORDER_DESC` nhưng cả `created` lẫn `updated` đều không giảm dần, kể cả khi tách riêng Mercari và Shops. Vài item đầu gần như theo `updated`, sau đó lẫn lộn |
| 3 | Trích được item id, title, price, url, thumbnail ổn định? | Có | 30/30 item parse đủ trường ở cả hai môi trường. Hai loại id: `m...` (Mercari, `/item/<id>`) và `2J...` (Shops, `itemType=ITEM_TYPE_BEYOND`, `/shops/product/<id>`) |
| 4 | Lấy 1–4 ảnh có cần mở trang chi tiết? | Có | Search trả 1 ảnh/item (`thumbnails` và `photos` đều dài 1). Detail `items/get` của `m22267384686` trả 10 ảnh riêng biệt. Detail của item Shops chưa thử |
| 5 | Ba môi trường phản hồi khác nhau thế nào? | Giống nhau về nội dung | Hai môi trường trả cùng 30 item, cùng thứ tự. VPS nhanh hơn ~2,4 lần (p50 0,103 s vs 0,246 s). Không môi trường nào bị chặn |
| 6 | Polling gap nào ổn định qua 30–50 chu kỳ? | 60 s/keyword | 50/50 (`OMEGA 168.005`) và 30/30 (`OMEGA`) chu kỳ ổn định trên VPS. Gap ngắn hơn chưa đo |
| 7 | Failure mode nào xuất hiện? | Không có từ phía Mercari | 0 CAPTCHA, 0 403, 0 429, 0 timeout, 0 lỗi schema. Chỉ 1 lỗi mạng local |
| 8 | Độ trễ từ lúc đăng đến lúc nhận alert? | ~2–3 phút với gap 60 s | `m89145414721` tạo lúc 16:11:45 UTC, có mặt ở vị trí 1 lúc 16:14:08 (≤ 2 phút 23 giây từ lúc đăng tới lúc search thấy). Chỉ một điểm đo. Cộng gap 60 s và gửi Telegram |
| 9 | Tốc độ listing mới mỗi ngày, theo từng keyword? | `OMEGA 168.005` ~0,03/ngày; `OMEGA` ~15–30/giờ | `OMEGA 168.005`: 30 item trải ~880 ngày, `numFound` = 35. `OMEGA`: ~23/29 item tạo trong 45 phút trước lần quét đầu (10 trong số đó là một lô Shops đăng cùng một phút); item đứng đầu đổi 7 lần trong 30 chu kỳ, có lúc đứng yên 14 phút. Ước lượng tự động của script (0,53/ngày) sai với keyword rộng, xem mục 4 |

Câu 9 quyết định hai thứ: số alert bạn thực sự nhận mỗi ngày, và gap an toàn.

## 3. Tốc độ listing theo keyword

| Keyword | Spread của 30 item đầu | Item/ngày ước tính |
|---|---|---|
| `OMEGA 168.005` | 2024-04-30 → 2026-09-28 (~880 ngày) | 0,03 |
| `OMEGA` | Đếm tay: ~23 item trong 45 phút | ~360–720 (15–30/giờ, theo đợt) |

Keyword thật sẽ nằm giữa hai cực này. Đo lại khi có danh sách keyword.

## 4. Failure mode quan sát được

| Hiện tượng | Tần suất | Cách xử lý trong code sản phẩm |
|---|---|---|
| Thứ tự kết quả không theo thời gian | Mọi chu kỳ | Dedup trên toàn bộ 30 id của trang, không dừng ở item đã thấy đầu tiên |
| Kết quả trộn Mercari (`m...`) và Shops (`2J...`) | Mọi chu kỳ (25/30 là Shops) | Mapper đọc `itemType` để dựng URL; detail ảnh cần đường riêng cho Shops |
| Search chỉ có 1 ảnh | Mọi item | Gọi detail khi có item mới để lấy 1–4 ảnh |
| `transport_error` sau khi máy sleep | 1/50, chỉ local | Backoff của `RetryingListingSource` là đủ |
| Item cũ bị đẩy lên đầu (sửa giá, sửa tin) | Thường gặp với keyword rộng, ví dụ `m80493943894` tạo 09-21 đứng thứ 3 | Id chưa từng thấy nên dedup theo id sẽ alert như item mới. **Đã quyết định (2026-09-28): chỉ alert item thật sự mới.** T17 bỏ qua item có `created` sớm hơn thời điểm baseline của rule, nhưng vẫn ghi id vào bảng dedup |
| Keyword khớp lỏng, cả mô tả | `OMEGA` trả cả đồ Kamen Rider Amazon Omega, thức ăn thú cưng, dầu dưỡng tóc | Không lọc trong code (ngoài scope). Người dùng đặt keyword cụ thể hơn |
| Ước lượng item/ngày từ spread `created` sai | Mọi keyword có item cũ bị đẩy lên | Không dùng spread `created` để tính tốc độ; đếm id mới giữa các chu kỳ |

## 5. Quyết định

**Nguồn dữ liệu chính:** ☒ HTTP + DPoP ☐ Playwright interception ☐ Proxy site

**Nguồn dự phòng:** Playwright interception, chưa dựng, chỉ làm nếu HTTP + DPoP
bị chặn về sau.

**Polling gap chốt:** 60 giây/keyword → latency p95 dự kiến ~61 giây

**VPS chốt:** VPS Siêu Tốc 1 GB, Nhật, AS22439 Perfect International | Chi phí ____/tháng

ASN này là hosting quốc tế, không thuộc nhóm nội địa Nhật trong `docs/VPS.md` §3,
nên xếp vào nhóm rủi ro cao hơn. Spike pass trên chính IP này, nhưng blocklist
của Mercari có thể đổi. Nếu về sau bị 403, thử ConoHa trước khi nghĩ tới proxy.

**Cần proxy JP không:** ☒ Không ☐ Có, chi phí ____/tháng

## 6. Đi tiếp hay dừng

☒ **GO** — lấy được item mới, đúng thứ tự thời gian, ổn định qua 50 chu kỳ, từ
IP của VPS Nhật sẽ dùng thật.

☐ **NO-GO** — chuyển phương án dự phòng, cộng thêm ____ ngày.

Ghi chú: Agent đề xuất **GO có điều kiện**, con người quyết định.

- Ổn định qua 50 chu kỳ từ IP VPS Nhật thật: đạt (50/50, 0 lỗi).
- "Đúng thứ tự thời gian": **không đạt** như định nghĩa, nhưng không chặn thiết
  kế, vì deduplication theo item ID trên cả trang 30 item không cần thứ tự.
  Rủi ro còn lại: một item mới bị đẩy ra ngoài 30 kết quả đầu trước khi bị quét.
  Với keyword hẹp (~35 kết quả) thì không xảy ra; keyword rộng cần đo lại.
- "Lấy được item mới": **đạt**. Với `OMEGA`, item đứng đầu đổi 7 lần trong 30
  phút; một item có mặt trong search chưa tới 2,5 phút sau khi đăng.
- Item cũ bị đẩy lên đầu (sửa giá, sửa tin): con người chọn **không alert**.
  Chỉ item có `created` sau thời điểm baseline của rule mới được alert. Ràng
  buộc này thuộc T17 `NewListingDetectionService`.
