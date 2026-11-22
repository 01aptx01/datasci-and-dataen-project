# Stitch comparison and browser verification

Captured at 1280 × 720 against the exported `inference_demo_01` and `inference_demo_stage_06_1` HTML. The reference HTML contains illustrative values; the app reads the verified Stage 06 snapshot.

The revised screenshot `app-portfolio-final.png` uses the reference date 2025-10-01 and B3: the verified 50/30/20 portfolio produces 4.441% annualized. The Replay daily and monthly screenshots show the revised layout; the exact data available as-of the chosen date determines which points are visible.

- Portfolio: 50/30/20 produced 8.128% annualized. 60/30/20 was rejected and displayed no risk; 60/20/20 produced 8.473%.
- Replay: 2025-10-01 initially withheld Actual. At target end 2025-10-08 it remained hidden until reveal, then showed 5.648% Actual and 1.438 percentage points absolute error. The source Pending row for 2026-09-25 stayed hidden even with reveal enabled and as-of 2026-10-02.
- The revised portfolio uses sliders and numeric inputs alongside the risk and ETF cards; its Replay link transfers the selected date and model. Replay has monthly and daily views and a 12-month strip. Other new pages summarize the snapshot and link to detailed legacy views.
- The graph suppresses forecasts later than the selected as-of date; consequently it can contain fewer points than the illustrative reference. The 5-day scale is an approximation using annualized volatility × √(5/252). The interface uses actual Stage 06 values rather than the prototype's illustrative data.
- Screenshots are viewport captures, not full-page captures. The prototype uses remote Tailwind and fonts; the application uses remote fonts with fallbacks. This is not a pixel-perfect acceptance result.
