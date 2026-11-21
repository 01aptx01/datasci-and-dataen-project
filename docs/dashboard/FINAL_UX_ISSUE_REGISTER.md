# DEDS Final Dashboard UX Issue Register

**Baseline:** `feat/dashboard-final-ux-acceptance` at `e5b637c`  
**Updated:** 2026-11-22 (Asia/Bangkok)

| ID | Priority | Route / area | Reproduction and evidence | Acceptance condition | Status |
|---|---|---|---|---|---|
| UX-01 | P0 | Forecasts / Replay | Scroll to selected forecast and same-date panel; Next is above viewport. Baseline activation required about 510px upward movement. | Five consecutive date steps update date, maturity, chart, and comparison with zero forced upward scrollbacks on desktop. | Open |
| UX-02 | P0 | Shared render / keyboard | Replay Next and invalid Scenario A edits rerender the whole root; focus returns to body or a different paired control. | Same-route updates retain the focused control, caret where supported, and viewport. Route changes start at a visible page heading. | Open |
| UX-03 | P0 | Portfolio / navigation | Replay→Portfolio preserves selection IDs/date/model but preserves scrollY≈947; title and selectors begin above the viewport. | Portfolio opens at its page context with exact selection retained; Back/Forward and refresh preserve the URL state. | Open |
| UX-04 | P0 | Portfolio / Scenario Lab | A/B editors precede comparison and timeline in one vertical column; selected-day delta and budget meaning are not visible while editing. | A/B editors, selected-day comparison, timeline, and budget status are reachable without repeated scrollbacks on desktop; mobile editing remains unobstructed. | Open |
| UX-05 | P0 | Shared typography / controls | Global tokens are 10–13px; key labels and controls use 11–13px. Some replay/portfolio controls are 32–40px high. | Important interpretation uses readable role tokens; controls meet 44px target and mobile targets prefer 48px where layout permits. | Open |
| UX-06 | P1 | Models | Metric and asset controls, chart, scope warning, and official/exploratory explanations span a long page; sampled labels reach 11px. | Each analysis keeps its controls, chart, N/scope, and caveat together; mobile values remain readable. | Open |
| UX-07 | P1 | Drift | Timeline and selected-observation details are in one long page and sampled supporting labels reach 11px. | Timeline and source-row inspector are grouped on desktop and stacked clearly on mobile, with explicit unavailable states. | Open |
| UX-08 | P1 | Research / Guide / Overview / Provenance | Long analytical pages contain 11–12px support text; README still calls this a D1–D7 dashboard and shell badge says D1–D2 foundation. | Thai-first guidance reflects the current eight-route D1–D9 product and keeps evidence scope adjacent to interpretation. | Open |
| UX-09 | P1 | Responsive / zoom / browser evidence | Baseline was measured at 1309×818 CSS pixels; requested 1440×900 did not produce that page viewport. Mobile widths, 200% zoom, and first-time-user study were not yet verified. | Record actual browser viewport, 360/390/430 mobile, 200% zoom, keyboard, console, and UAT evidence; document unavailable participant study. | Open |
