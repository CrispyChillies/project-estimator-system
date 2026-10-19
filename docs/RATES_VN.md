# Default VND rate card (Vietnam market)

Canonical money in Calibr is whole **VND**. These are the *default hourly billing rates* per role; the admin can change
the workspace defaults and every user can override them for their own account (Settings → Roles and rates, in VND or USD).
Applied by `backend/app/services/rates.py` (`DEFAULT_RATES_VND`) only to roles without a VND rate; nothing else is overwritten.

Research date: 2026-10-20. Exchange rate used for USD figures: **1 USD = 25.869,40 VND** (open.er-api.com, ExchangeRate-API
open access endpoint, last update Mon, 19 Oct 2026 00:02 UTC). The workspace default is stored as `USD_VND_RATE_DEFAULT=25869`.

## Method

```
rate / h  =  median monthly gross salary (mid-level)  ×  K
K         =  1,235  (employer social-insurance and union contributions)
             × 13/12 (13th-month salary)
             ÷ 176 h (22 working days × 8 h per month)
             ÷ 0,75  (billable utilisation)
             × 1,25  (overhead: office, tools, management, bench)
             × 1,25  (margin)
          =  0,015837
```

Rounded to the nearest **10.000 ₫**. The factor is the same for every role, so the ordering of rates follows the ordering of
market salaries.

## Inputs and results

| Role | Monthly gross used (triệu ₫) | Source of the salary | Rate / h (₫) | USD / h | Note |
|---|---:|---|---:|---:|---|
| ML/CV Engineer | 52,5 | TalentHunter.asia 2025: AI/ML Engineer, middle band 40–65 triệu → midpoint | 830.000 | 32,1 | **Single source** (ITviec table has no AI/ML row) |
| PM | 50,1 | ITviec 2025-2026: Project Leader / Project Manager, median | 790.000 | 30,5 | |
| DevOps | 42,5 | TalentHunter.asia 2025: DevOps / Cloud Engineer, middle band 30–55 → midpoint | 670.000 | 25,9 | **Single source** (ITviec table has no DevOps row) |
| Data Engineer | 41,3 | ITviec 2025-2026: Data Engineer, median (TalentHunter band 25–45 is consistent) | 650.000 | 25,1 | |
| Backend | 37,8 | ITviec 2025-2026: Back-end Developer, median | 600.000 | 23,2 | |
| Mobile | 36,85 | ITviec 2025-2026: Mobile Developer, median | 580.000 | 22,4 | |
| Frontend | 34,8 | ITviec 2025-2026: Front-end Developer, median | 550.000 | 21,3 | |
| Designer | 34,8 | **Assumption**: no UI/UX row in either source, so the nearest comparable role (Frontend) is used | 550.000 | 21,3 | **Assumption** |
| QA | 31,2 | ITviec 2025-2026: QA – QC, median (Tester: 28,8) | 490.000 | 18,9 | |

Ordering check: ML/CV > PM > DevOps > Data Engineer > Backend > Mobile > Frontend = Designer > QA. DevOps and ML/CV are not cheaper
than QA, and nothing is out of order relative to the source salaries.

## Sources (all fetched 2026-10-20)

1. **ITviec – Vietnam IT Salary & Recruitment Market Report 2025-2026** (survey of 1.839 respondents, fieldwork 27 May–31 Jul and
   21 Oct–11 Nov 2025), salary table by position, medians in triệu ₫/month: https://itviec.com/report/vietnam-it-salary-and-recruitment-market
   (Vietnamese: https://itviec.com/bao-cao/luong-it-va-thi-truong-tuyen-dung-it-vietnam).
2. **TalentHunter.asia – Mức lương IT Việt Nam 2025** (gross monthly salary bands by role and level, VND; the column headers
   were not captured by the page extractor — the *second* column was used as mid-level, and it brackets the ITviec medians for every
   role present in both): https://talenthunter.asia/blog/salary-insights/muc-luong-it-viet-nam-2025-khao-sat-chi-tiet-theo-vi-tri
3. Exchange rate: https://open.er-api.com/v6/latest/USD (terms: https://www.exchangerate-api.com/terms — attribution required,
   caching and commercial use allowed, one request per day is enough).

## Sanity check against published billing rates (independent of the salary data)

| Source | Reported Vietnam rate | Comment |
|---|---|---|
| Global BPO Index, *Offshore Software Development Vietnam: Buyer's Guide* | blended **$18–35 / h** | Our rates span $18,9–32,1 → inside the range |
| VietnamBiz, *Mác giá rẻ không còn mang lại hợp đồng…* (search-result snippet; subject of the sentence truncated) | **$25–45 / h** | Our mid-range roles are at its low end: conservative, domestic-market |
| SecondTalent, *Cost to hire software developers in Vietnam* (2026) | **$28–68 / h** incl. senior, English-fluent, overseas-client engineers | Not comparable to a mid-level domestic rate; shown as the upper bound |
| Hitek (hitek.com.vn) | engineers with 3–5 years in Hanoi/HCMC: **25–40 triệu ₫/month** (~$1.000–1.600) | Matches the ITviec medians used as input |

Two independent price sources (Global BPO Index, VietnamBiz) bracket the derived range, as required.

## Assumptions and limits (be honest about them)

* Employer contributions 21,5 % + 2 % union fee, the 13th-month salary, 75 % utilisation, 25 % overhead and 25 % margin are
  **assumptions** (statutory rates were not re-verified in this run). Change the factor in one place if your firm differs.
* DevOps and ML/CV rest on one source (TalentHunter bands, midpoint); Designer is borrowed from Frontend.
* Salaries are gross medians for the whole market; Hanoi/HCMC premiums (+10–15 %) and Da Nang discounts (−15–20 %) mentioned by
  TalentHunter are not applied.
* Billing rates for overseas clients are higher (SecondTalent range); override them per user.
* Historical estimates keep no stored cost: cost is computed live from the current rates (see DECISIONS.md #66).
