# Task board

Trạng thái: `todo` -> `in-progress` -> `review` -> `merged`.

Chỉ con người đổi trạng thái sang `merged`. Agent chỉ được đổi sang `review`.

Task cùng một Wave có tập file không giao nhau nên chạy song song được ở các
session khác nhau. Mỗi session một git worktree riêng.

```
git worktree add ../mab-T07 -b feature/listing-repository
cd ../mab-T07 && claude
```

---

## Wave 0 — Gate

Không viết một dòng code sản phẩm nào cho tới khi T00 xong và ô GO trong
`docs/SPIKE.md` được tick.

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T00 | `chore/spike` | Script dò Mercari, chạy local + VPS Nhật, điền SPIKE.md | — | 4–8 | todo |

## Wave 1 — Nền móng, chạy một mình

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T01 | `chore/scaffold` | Cây thư mục, pyproject, ruff, mypy, pytest, Makefile, pre-commit | T00 | 2 | todo |

## Wave 2 — song song ×3

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T02 | `feature/shared-kernel` | `shared/`: clock, structured logging, jitter helper | T01 | 1.5 | todo |
| T03 | `feature/domain-models` | `domain/models/`: ItemId, Listing, KeywordRule, JpyAmount, errors | T01 | 2 | todo |
| T04 | `feature/settings` | `EnvSettings` qua pydantic-settings, `.env.example` | T01 | 1 | todo |

## Wave 3 — song song ×2

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T05 | `feature/domain-ports` | 4 Protocol: ListingSource, ListingRepository, KeywordRuleRepository, Notifier | T03 | 1.5 | todo |
| T06 | `feature/db-schema` | Migration SQLite, bật WAL, connection factory | T01, T04 | 2 | todo |

## Wave 4 — song song ×4

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T07 | `feature/listing-repository` | `SqliteListingRepository` + test dedup qua restart | T05, T06 | 3 | todo |
| T08 | `feature/keyword-repository` | `SqliteKeywordRuleRepository`, CRUD đầy đủ, import seed YAML khi bảng rỗng, export YAML | T05, T06 | 2.5 | todo |
| T09 | `feature/dpop-factory` | `DpopProofFactory` ES256 theo RFC 9449 + test | T02 | 2 | todo |
| T10 | `feature/telegram-client` | Client mỏng trên Bot API + test respx | T04 | 2 | todo |

## Wave 5 — song song ×3

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T11 | `feature/mercari-mapper` | `MercariSearchResponseMapper` + fixture thật từ spike | T03, T05 | 2.5 | todo |
| T12 | `feature/notification-payload` | `NotificationPayload`, format giờ ICT, dựng caption | T03 | 1.5 | todo |
| T13 | `feature/retry-decorator` | `RetryingListingSource`, backoff mũ có jitter | T05, T02 | 2 | todo |

## Wave 6 — song song ×2

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T14 | `feature/mercari-http-source` | Strategy chính, gọi search + detail | T09, T11 | 3 | todo |
| T15 | `feature/telegram-notifier` | Chuỗi media group -> single photo -> text | T10, T12 | 3 | todo |

## Wave 7 — song song ×2

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T16 | `feature/baseline-seeding` | `BaselineSeedingService`, baseline **theo từng rule**: rule mới thêm lúc nào cũng seed riêng, không bắn alert | T07 | 2 | todo |
| T17 | `feature/detection-service` | `NewListingDetectionService`, chọn item chưa thấy | T07 | 2 | todo |

## Wave 8 — song song ×2

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T18 | `feature/scan-cycle` | `ScanCycleService`, **nạp lại rule từ repository mỗi chu kỳ**, cô lập lỗi từng rule, gộp item khớp nhiều rule | T14, T15, T16, T17 | 3.5 | todo |
| T19 | `feature/health-monitor` | Cảnh báo 0 kết quả toàn cục, lỗi liên tiếp, có cooldown | T15, T05 | 2.5 | todo |

## Wave 9 — tuần tự

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T20 | `feature/scheduler` | `IntervalScheduler` có jitter, dừng êm khi SIGTERM | T02, T18 | 2 | todo |
| T21 | `feature/composition-root` | Wiring DI, `__main__`, graceful shutdown | T18, T19, T20 | 2.5 | todo |

## Wave 10 — Web UI, song song ×4 sau T22

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T22 | `feature/web-skeleton` | FastAPI app factory, lifespan chạy scanner nền, mount static | T21 | 2 | todo |
| T23 | `feature/api-keywords` | Controller CRUD keyword, bật/tắt, reset baseline, tự seed lại khi sửa `query` | T22, T08 | 2.5 | todo |
| T24 | `feature/api-settings` | Controller sửa polling gap, ngưỡng cảnh báo, số ảnh tối đa | T22, T08 | 2 | todo |
| T25 | `feature/api-status` | Controller trạng thái: chu kỳ cuối, lỗi, listing gần đây | T22, T07 | 2 | todo |
| T26 | `feature/api-actions` | Gửi alert thử, import/export YAML, reset baseline một rule | T22, T15 | 2 | todo |

## Wave 11 — tuần tự

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T27 | `feature/ui-page` | Một trang HTML + JS thuần, không build step, 4 khối UI | T23, T24, T25, T26 | 4 | todo |

## Wave 12 — song song ×3

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T28 | `test/e2e-fake-source` | Test đầu-cuối qua service thật với source giả | T21 | 3 | todo |
| T29 | `feature/healthcheck` | `/healthz` + module healthcheck cho Docker | T22 | 1.5 | todo |
| T30 | `chore/docker` | Dockerfile multi-stage, compose, named volume, expose UI | T21 | 2.5 | todo |

## Wave 13 — tuần tự

| ID | Branch | Việc | Phụ thuộc | Giờ | Trạng thái |
|---|---|---|---|---|---|
| T31 | `test/acceptance-local` | Chạy đủ 11 mục checklist + 4 chaos test trên máy local | T28, T29, T30 | 3 | todo |
| T32 | `chore/operator-guide` | README vận hành cho người không phải dev | T31 | 1.5 | todo |
| T33 | `chore/vps-deploy` | Chạy `deploy/bootstrap.sh`, deploy theo `docs/VPS.md`, đặt cron backup, mở soak 48h | T31, T32 | 3 | todo |

---

## Tổng

34 task, **65–80 giờ công**.

## Đường găng

`T00 -> T01 -> T03 -> T05 -> T07 -> T17 -> T18 -> T20 -> T21 -> T22 -> T23 -> T27 -> T31 -> T33`

Song song không rút ngắn được đường găng, và review của con người thì tuần tự.
Đó mới là nút cổ chai thật, không phải số session chạy đồng thời.

## Ghi chú về UI

UI nằm ngoài scope của spec gốc (§6.2). Nó thêm 6 task và ~14 giờ. Nếu muốn về
đích nhanh nhất, cắt Wave 10 và 11, chạy T00–T21 rồi T28–T33: còn **48–58 giờ**
và keyword sửa qua YAML như thiết kế ban đầu. UI có thể bổ sung sau mà không
phải sửa gì ở domain hay application, vì controller chỉ gọi service có sẵn.
