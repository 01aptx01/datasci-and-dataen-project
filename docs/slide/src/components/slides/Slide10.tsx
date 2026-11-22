import React from 'react';
import {
  COURSE_INFO, EXPERIMENT_IDENTITY, H1_RESULTS, H2_H3_RESULTS,
  MODEL_METRICS_TEST, PORTFOLIO_PRESETS, RESULT_SLIDES, SLIDE_TITLES,
  TEAM_MEMBERS,
} from '../../data/reportData';
import { Fraction, MathBox, Radical, SlideFrame, Summation } from '../SlideChrome';
import {
  EtfUniverseInteractive, H1ToH3StatsLab, MaturityTimelineWidget,
  ModelMaeChart, ModelsAndSplitLab, OnlineSgdMonitoringLab,
  PortfolioBudgetLab, PortfolioScenarioLab, SavedReplayMiniLab,
  UnifiedPipelineDiagram,
} from '../SlideVisuals';
import { ReturnVsVolToggle, PortfolioBridgeSteps, LimitationsStaticGrid } from '../SlideHelpers';
import type { SlideContextProps } from '../Slides';

export function Slide10({ h1ScatterRows }: SlideContextProps) {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(10);
  return (
        <SlideFrame
          slideNumber={10}
          totalSlides={total}
          title={SLIDE_TITLES[9]}
          subtitle="H2 & H3 (Block Bootstrap + Holm บน Test) และ H1 (OLS + HAC lag 5 บน Train)"
          showSourceFooter={showFooter}
        >
          <div className="grid flex-1 grid-cols-12 gap-6 py-2">
            <div className="col-span-5 flex h-full flex-col justify-between gap-3.5">
              <div className="flex flex-1 flex-col justify-center rounded-xl border border-zinc-200 bg-white p-5">
                <div className="text-[15px] font-bold text-zinc-900">
                  ผล H1 (Train · N = 752 / ETF)
                </div>
                <div className="font-mono-num mt-3 grid grid-cols-3 gap-2.5 text-center text-[13.5px]">
                  {H1_RESULTS.map((r) => (
                    <div key={r.ticker} className="rounded-lg bg-zinc-50 px-2 py-2.5">
                      <div className="font-bold text-[#9E0B0F]">{r.ticker}</div>
                      <div className="mt-0.5 font-semibold">β = {r.beta.toFixed(3)}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-3 text-[13.5px] text-zinc-600">
                  ปฏิเสธ H₀ ทั้ง 3 กอง (เป็นความสัมพันธ์เชิงสถิติ ไม่ใช่เหตุและผล)
                </div>
              </div>

              <div className="flex flex-col gap-3">
                {H2_H3_RESULTS.map((r) => (
                  <div key={r.id} className="rounded-xl border border-zinc-200 bg-zinc-50 px-5 py-4">
                    <div className="flex items-center justify-between">
                      <span className="text-[15px] font-bold text-[#9E0B0F]">{r.labelTh}</span>
                      <span className="rounded bg-emerald-100 px-2.5 py-0.5 text-[12.5px] font-bold text-emerald-800">
                        {r.decision}
                      </span>
                    </div>
                    <div className="font-mono-num mt-1.5 text-[13.5px] text-zinc-700">
                      ΔMAE +{r.deltaMae.toFixed(6)} · adj. p = {r.adjustedP.toFixed(6)}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="col-span-7 h-full">
              <H1ToH3StatsLab scatterRows={h1ScatterRows} />
            </div>
          </div>
        </SlideFrame>
  );
}
