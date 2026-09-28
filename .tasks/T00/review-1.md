verdict: PASS
summary: The probe script does everything the plan asks, stays inside the CLAUDE.md section 2 guardrails (no login, no cookies, sequential, no retries), has no comments, and passes ruff and mypy --strict; docs/SPIKE.md records both environments from the real VPS IP with the GO decision and its documented exception on ordering. Remaining findings are minor accuracy and auditability issues in a throwaway script and report, none of which change the GO conclusion.

reviewer_note: This review was run in the same session that wrote the code, so it is not independent. The human should read spike/probe_mercari.py and docs/SPIKE.md sections 2, 4 and 6 directly before merging.

gates_note: `make gates` does not apply to this task. It targets src/ and tests/, which do not exist until T01. Equivalent checks run on the script: `ruff check spike`, `ruff format --check spike` and `mypy --strict --config-file /dev/null spike/probe_mercari.py` all pass. The `--config-file /dev/null` is needed because pyproject.toml loads the pydantic.mypy plugin, which is not installed before T01.

findings:
  - id: F1
    severity: minor
    file: spike/probe_mercari.py
    anchor: f"search thumbnails={int(detail_candidate.thumbnail_url is not None)}"
    problem: The label says "search thumbnails" but the value is 0 or 1 depending on whether a first thumbnail exists, not how many thumbnails search returned. It would print 1 even if search returned four. The SPIKE.md claim "Search trả 1 ảnh/item" is actually backed by an ad-hoc check outside the script, not by this line.
    fix: Add a field `thumbnail_count: int` to `ProbedListing`, set it in `parse_listing` to `len(thumbnails) if isinstance(thumbnails, list) else 0`, and print `search thumbnails={detail_candidate.thumbnail_count}` instead.

  - id: F2
    severity: minor
    file: spike/probe_mercari.py
    anchor: def estimate_listings_per_day(listings: Sequence[ProbedListing]) -> float | None:
    problem: The estimate divides by the spread between the oldest and newest `created` on the page. Mercari pushes old edited or price-dropped items back into the results, so for a broad keyword the spread covers weeks and the estimate is off by roughly 1000x (printed 0.53/day for `OMEGA`, real rate about 15–30/hour). docs/SPIKE.md section 4 already records this and gives hand-counted numbers, so the report is correct; only the script output is misleading.
    fix: No code change required for a throwaway script. If it is rerun for new keywords, count distinct new item ids between the first and last cycle and divide by elapsed time, instead of using `estimate_listings_per_day`.

  - id: F3
    severity: minor
    file: spike/probe_mercari.py
    anchor: detail_candidate = next(
    problem: The detail probe only ever fetches a regular Mercari item (`m...`), found by checking the URL prefix. Shops items (`2J...`, itemType `ITEM_TYPE_BEYOND`) were 25 of 30 results for `OMEGA 168.005`, and nothing tells us whether `items/get` works for them. Question 4 in docs/SPIKE.md already says the Shops detail is untested, so T14 has to find the Shops photo endpoint itself. Picking the item by URL prefix is also an indirect way to test item type.
    fix: No change in this branch. Carry it forward: T14's plan must include a spike-style check of photo retrieval for an `ITEM_TYPE_BEYOND` item before building the detail call.

  - id: F4
    severity: minor
    file: docs/SPIKE.md
    anchor: **VPS chốt:** VPS Siêu Tốc 1 GB, Nhật, AS22439 Perfect International | Chi phí ____/tháng
    problem: The monthly cost is still blank, and the local column's IP / ASN says "ASN chưa ghi". Neither affects the decision (the local column is only a reference), but the report is not fully filled in.
    fix: Replace `____` with the actual monthly price from the VPS Siêu Tốc invoice. Leave the local ASN as is, or fill it from `curl -s https://ipinfo.io` run on the local machine.

  - id: F5
    severity: minor
    file: docs/SPIKE.md
    anchor: | 2 | Ép được thứ tự mới-nhất-trước thật sự? | **Không** |
    problem: The evidence that neither `created` nor `updated` is descending, even when split by Mercari and Shops, comes from two ad-hoc terminal checks that are not in the script and whose output was not saved. A later reader cannot reproduce the `updated` half of this claim from the committed code.
    fix: No change in this branch. Carry it forward: T11's plan (MercariSearchResponseMapper) should include a recorded fixture with both `created` and `updated`, which is where this evidence becomes permanent.

  - id: F6
    severity: minor
    file: .tasks/T00/plan.md
    anchor: ## Commit sequence
    problem: The plan listed three commits. The branch has six: the three planned ones plus `chore(spike): mark t00 blocked on vps run`, `docs(spike): record broad keyword run on vps` and `docs(spike): record alert only truly new listings decision`. All three are Conventional Commits and are justified by work the human asked for (VPS wait, broad keyword run, product decision), but they are outside the approved plan.
    fix: No change. The human should note the extra commits when reading the branch.

  - id: F7
    severity: minor
    file: docs/SPIKE.md
    anchor: ☒ **GO** — lấy được item mới, đúng thứ tự thời gian, ổn định qua 50 chu kỳ, từ
    problem: The ticked GO line still claims "đúng thứ tự thời gian" (correct chronological order), which the spike showed to be false. The exception is explained in the Ghi chú below it, but the ticked line alone reads as if every condition was met.
    fix: Append to the end of the GO paragraph, on the line after "IP của VPS Nhật sẽ dùng thật.", the sentence: `Ngoại lệ: thứ tự thời gian không đạt, chấp nhận vì dedup theo item ID trên cả trang (xem Ghi chú).`
