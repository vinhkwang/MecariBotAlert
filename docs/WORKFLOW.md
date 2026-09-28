# Quy trình làm việc

## Vòng lặp một task

```
/next-task T07        opus    lập plan, tạo branch        -> BẠN DUYỆT PLAN
/implement T07        sonnet  viết code + test, commit
/verify               haiku   chạy hết các cổng chất lượng
/review T07           opus    soi diff, ghi review-1.md   -> verdict
/fix T07              sonnet  áp dụng finding
/verify               haiku
/review T07           opus    -> PASS?
/finish T07           sonnet  đẩy branch, đổi trạng thái  -> BẠN REVIEW + MERGE
```

Lặp `/review` -> `/fix` -> `/verify` cho tới khi `PASS`. Nếu tới lần
`CHANGES_REQUESTED` thứ ba thì dừng: plan sai chứ không phải code sai, quay lại
`/plan`.

## Quyền của agent

`.claude/settings.json` (commit vào repo, cả team dùng chung) tự động cho phép
vòng lặp thường ngày — `make`, git đọc/ghi/commit/push, pytest, ruff, mypy — nên
session không dừng hỏi mỗi lệnh. Chạy song song ba worktree mà cứ bị hỏi thì
không ai làm được gì.

Danh sách `deny` mới là phần đáng chú ý:

| Bị chặn | Vì sao |
|---|---|
| `git merge`, `gh pr merge` | Biến quy tắc "agent không bao giờ merge" thành cơ chế, không chỉ là câu chữ trong CLAUDE.md |
| `git push --force`, `-f`, `--force-with-lease` | Một branch đang chờ bạn review bị ghi đè là mất dấu vết review |
| `git reset --hard` | Xoá công việc chưa commit của chính nó |
| `git commit --no-verify` | Đường vòng qua pre-commit hook |
| `Read(./.env)` | Agent không cần token thật để viết code |

Đây là hàng rào chống nhầm lẫn, không phải biên giới bảo mật. Có báo cáo một số
client bỏ qua permission rule, và một agent bị chặn ở Bash vẫn có thể thử lối
khác. **Cổng thật vẫn là bạn review trước khi merge.** Đừng nới `deny` ra chỉ vì
nó chặn một lệnh bạn đang cần — sửa việc cần làm thì đúng hơn.

Muốn nới quyền cho riêng máy mình thì dùng `.claude/settings.local.json`, file
này đã nằm trong `.gitignore`. Nhưng `deny` ở cấp user (`~/.claude/settings.json`)
vẫn thắng `allow` ở cấp project, nên nếu một lệnh bị chặn khó hiểu, kiểm tra
settings cá nhân trước.

## Vì sao handoff phải qua file

`/review` chạy bằng opus, `/fix` chạy bằng sonnet, và chúng có thể ở hai session
khác nhau. Model rẻ không nhìn thấy hội thoại của model đắt. Nên mọi thứ quan
trọng phải nằm trong `.tasks/<ID>/`:

```
.tasks/T07/
  plan.md        plan đã duyệt
  review-1.md    findings vòng 1
  review-2.md    findings vòng 2
  state.md       phase: reviewed, verdict: CHANGES_REQUESTED, round: 2
```

Mỗi finding trong review file phải tự đủ nghĩa: file, vị trí neo, vấn đề, và
cách sửa chính xác. Nếu model rẻ phải suy đoán thì finding viết chưa đạt.

## Chi phí

Model đắt chỉ đọc và viết văn bản, không sinh code. Model rẻ sinh code, vốn là
phần tốn token nhất. Tỉ lệ token thực tế thường rơi vào khoảng 15–25% cho khâu
plan và review, phần còn lại cho implement và fix.

Nếu muốn tiết kiệm thêm: hạ `/plan` xuống sonnet. Tôi để opus vì plan sai sẽ
kéo theo ba vòng review, đắt hơn nhiều so với tiền tiết kiệm được ở khâu plan.
Còn `/review` thì đừng hạ — đó là chỗ duy nhất bắt được lỗi kiến trúc.

## Chạy song song

Mỗi session một worktree, không dùng chung thư mục làm việc:

```
git worktree add ../mab-T07 -b feature/listing-repository
git worktree add ../mab-T09 -b feature/dpop-factory
git worktree add ../mab-T10 -b feature/telegram-client
```

Mỗi thư mục mở một cửa sổ terminal riêng, chạy `claude` trong đó.

Chỉ chạy song song các task cùng Wave trong `docs/TASKS.md` — chúng được xếp sao
cho tập file không giao nhau. Task khác Wave thì phụ thuộc nhau, chạy song song
sẽ dẫn tới conflict và review lại từ đầu.

Ba session là con số hợp lý. Nhiều hơn thì bạn thành nút cổ chai, vì mọi branch
đều phải qua mắt bạn trước khi merge.

Xoá worktree sau khi merge:

```
git worktree remove ../mab-T07
```

## Giao thức merge

Agent **không bao giờ** merge. Khi `/finish` xong, branch đã được đẩy lên remote
và trạng thái task đổi thành `review`. Bạn làm phần còn lại:

```
git checkout main
git pull
git merge --no-ff feature/listing-repository
git push
```

Trước khi merge, đọc ít nhất: diff của `src/`, file test mới, và mục `minor`
chưa sửa trong review file cuối cùng.

Sau khi merge, tự tay đổi trạng thái task trong `docs/TASKS.md` thành `merged`.
Đây là thao tác duy nhất của bạn mà agent không được làm thay — vì `/next-task`
dựa vào nó để biết task nào đã sẵn sàng.

## Thứ tự chạy thực tế

```
Ngày 1   /spike, chạy 3 nơi, điền SPIKE.md, tick GO
         T01 scaffold
Ngày 2   T02 T03 T04 song song  ->  T05 T06 song song
Ngày 3   T07 T08 T09 T10 song song  ->  T11 T12 T13 song song
Ngày 4   T14 T15  ->  T16 T17  ->  T18 T19
Ngày 5   T20 T21  ->  T22  ->  T23 T24 T25 T26 song song
Ngày 6   T27 UI  ->  T28 T29 T30 song song
Ngày 7   T31 acceptance local, T32 docs
Ngày 8   T33 deploy VPS, mở soak
Ngày 9-10  soak 48h, sửa lỗi phát sinh
```

Nhanh nhất **8 ngày tới lúc deploy**, **10 ngày tới lúc nghiệm thu xong**.

Bỏ UI (Wave 10, 11) thì rút còn **6 ngày tới deploy, 8 ngày tới nghiệm thu**.
