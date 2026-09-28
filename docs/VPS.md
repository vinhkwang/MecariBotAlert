# Cấu hình VPS

## 1. Tải thực tế của bot

Trước khi chọn máy, nhìn xem nó thực sự làm gì:

- Một process Python: uvicorn phục vụ UI + một asyncio task quét nền.
- 10 keyword, mỗi ~18 giây một HTTP request. Tức là **khoảng 3 request/phút**.
- Chỉ khi có item mới mới gọi thêm trang chi tiết và tải 1–4 ảnh.
- SQLite vài chục MB sau cả năm.
- UI một người dùng, thỉnh thoảng mở.

Đây là workload **I/O bound và gần như rảnh**. CPU nằm im 97% thời gian. Đừng
mua máy to.

## 2. Cấu hình

| | Tối thiểu | Khuyến nghị | Nếu phải dùng Playwright |
|---|---|---|---|
| vCPU | 1 | 1 | 2 |
| RAM | 1 GB | **2 GB** | 4 GB |
| Disk | 20 GB SSD | 25–30 GB SSD | 40 GB SSD |
| Băng thông | 100 GB/tháng | — | — |
| IPv4 | bắt buộc | bắt buộc | bắt buộc |

**RAM.** Process Python chiếm ~150–200 MB RSS. Docker daemon ~60 MB. Debian tối
giản ~150 MB. Tổng khoảng 400–500 MB. 1 GB chạy được nhưng build image ngay trên
máy sẽ chật; 2 GB cho bạn chỗ thở và không đắt hơn bao nhiêu.

**Playwright là lý do duy nhất cần máy to hơn.** Chromium headless ăn thêm
400–600 MB và ~1 GB đĩa. Chỉ nâng cấp nếu spike kết luận phải dùng nó — đừng
mua trước.

**Băng thông.** Search response ~20–50 KB × ~5.000–7.000 lượt/ngày ≈ 150–350
MB/ngày. Cộng ảnh (tải về rồi đẩy lên Telegram, tính hai chiều) ≈ **10–15
GB/tháng**. Mọi gói VPS Nhật đều thừa sức. Không phải yếu tố cần cân nhắc.

**IPv4 bắt buộc.** Vài gói rẻ chỉ có IPv6. Không dùng được.

## 3. Chọn nhà cung cấp — có một mâu thuẫn bạn cần biết

Nhà cung cấp có ASN sạch nhất lại là nhà khó đăng ký nhất với người ở Việt Nam.

**Nhóm nội địa Nhật — reputation tốt nhất:**
さくらのVPS, ConoHa (GMO), Xserver VPS, KAGOYA, WebARENA Indigo.
Dải IP của họ phục vụ rất nhiều doanh nghiệp Nhật hợp pháp nên ít bị gắn cờ.
Nhược điểm: phần lớn hướng tới khách trong nước, một số yêu cầu địa chỉ hoặc
thẻ Nhật, và đăng ký từ IP nước ngoài có thể kích hoạt khoá bảo mật tạm thời.

Có báo cáo ConoHa đăng ký được từ nước ngoài, thanh toán thẻ hoặc Amazon Pay và
kích hoạt ngay. Đây là thông tin từ người dùng, không phải cam kết của nhà cung
cấp — kiểm tra trước khi đặt kỳ vọng.

**Nhóm nước ngoài có datacenter Tokyo — dễ đăng ký, reputation kém hơn:**
Vultr, Linode/Akamai, DigitalOcean, Kamatera.
Vị trí là Nhật nhưng ASN là hosting quốc tế, bị scraper dùng nhiều, nằm trong
blocklist thương mại — **cùng loại vấn đề với AWS**. Nếu đã loại AWS vì lý do
ASN thì không thể chọn nhóm này mà không thừa nhận đang chấp nhận rủi ro tương
tự, chỉ nhẹ hơn một bậc.

### Cách quyết định

1. Thử đăng ký ConoHa trước. Nó có **tính tiền theo giờ** — dựng máy, chạy
   spike, vài trăm yên là biết kết quả.
2. Spike pass thì mới chuyển sang gói tháng hoặc năm.
3. Đăng ký không được thì lấy Vultr Tokyo, nhưng **chạy spike trước khi trả
   tiền dài hạn**, và ghi rõ vào SPIKE.md rằng nguồn IP thuộc nhóm rủi ro cao.
4. Cả hai đều fail thì vấn đề không phải VPS. Lúc đó mới tính tới proxy JP dân
   cư, và đó là quyết định hạ tầng riêng, không phải thứ nhét vào code.

**Đừng trả tiền một năm trước khi spike xanh.** Giá theo năm rẻ hơn ~30%, nhưng
mua nhầm một con IP bị chặn thì tiết kiệm đó thành lỗ hoàn toàn.

## 4. Chuẩn bị máy

`deploy/bootstrap.sh` làm hết phần này. Chạy một lần, bằng root, trên máy vừa
dựng:

```bash
scp deploy/bootstrap.sh root@<vps-ip>:/tmp/
ssh root@<vps-ip> 'bash /tmp/bootstrap.sh <your-username> "<your-ssh-public-key>"'
```

Nó làm:

- Tạo user thường có sudo, cài SSH key.
- Khoá SSH: tắt đăng nhập root, tắt đăng nhập mật khẩu, chỉ còn key.
- `ufw`: chặn hết inbound trừ SSH. **Không mở cổng 8080.**
- `fail2ban` cho SSH.
- Bật `unattended-upgrades` để vá bảo mật tự động.
- Tạo swapfile 1 GB làm phao cứu sinh chống OOM.
- Cài Docker Engine và compose plugin.
- Đặt timezone máy về UTC. Code lưu UTC và hiển thị ICT; đừng để giờ máy xen
  vào giữa.

## 5. UI không bao giờ mở ra internet

Cổng 8080 không nằm trong ufw allow list và compose đã bind `127.0.0.1:8080`.
Truy cập từ máy bạn:

```bash
ssh -L 8080:127.0.0.1:8080 <user>@<vps-ip>
```

Rồi mở `http://127.0.0.1:8080`. Không cần domain, không cần TLS, không cần
đăng nhập — vì không có gì để tấn công từ bên ngoài.

Nếu có lúc nào bạn định mở cổng này ra ngoài: đừng. Đó là trang sửa được
keyword và bắn được thông báo, sau một IP không ai canh.

## 6. Vận hành

```bash
cd ~/mercari-alert-bot
docker compose up -d --build
docker compose logs -f
docker compose ps
```

Docker đã bật systemd nên container tự lên lại sau reboot nhờ
`restart: unless-stopped`.

Sao lưu database, đặt cron hàng ngày:

```bash
crontab -e
0 3 * * * /home/<user>/mercari-alert-bot/deploy/backup.sh >> /var/log/mab-backup.log 2>&1
```

`backup.sh` dùng SQLite online backup API nên an toàn khi bot đang ghi. Copy
thẳng file `.db` lúc WAL đang hoạt động thì có thể ra bản sao hỏng.

## 7. Theo dõi trong 48 giờ soak

```bash
free -m                                   # RAM còn bao nhiêu
df -h                                     # đĩa
docker stats --no-stream                  # process ăn bao nhiêu
docker compose logs --since 1h | grep -c error
```

Nếu RSS của container tăng đều theo giờ mà không đứng lại, đó là rò rỉ bộ nhớ,
không phải thiếu RAM. Nâng cấp máy sẽ chỉ làm nó chết chậm hơn.
