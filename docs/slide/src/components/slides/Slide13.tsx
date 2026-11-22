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

export function Slide13({ weightsB, portfolioRows }: SlideContextProps) {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(13);
  return (
        <SlideFrame
          slideNumber={13}
          totalSlides={total}
          title={SLIDE_TITLES[12]}
          subtitle="เปรียบเทียบ Scenario A และ B กับเพดานความผันผวนต่อปีที่ตั้งไว้"
          showSourceFooter={showFooter}
        >
          <div className="grid flex-1 grid-cols-12 gap-6 py-2">
            <div className="col-span-5 flex h-full flex-col justify-between gap-4">
              <div className="flex flex-1 flex-col justify-center rounded-xl border border-zinc-200 bg-white p-5.5">
                <h3 className="font-display text-[19px] font-bold text-[#9E0B0F]">
                  การเทียบนโยบายความผันผวน (Budget)
                </h3>
                <p className="mt-3 text-[15.5px] leading-relaxed text-zinc-800">
                  กำหนดเพดานความผันผวนต่อปีที่ยอมรับได้ เพื่อเทียบพอร์ต A และ B ว่าสัดส่วนใดต่ำกว่า เท่ากับ หรือเกินงบที่ตั้งไว้
                </p>
                <div className="mt-4 rounded-xl bg-zinc-50 px-4 py-3 text-[14px] text-zinc-700">
                  <strong>สัดส่วน B ปัจจุบัน:</strong>{' '}
                  <span className="font-mono-num font-bold text-[#9E0B0F]">
                    SPY {weightsB.SPY.toFixed(1)}% · IEF {weightsB.IEF.toFixed(1)}% · GLD {weightsB.GLD.toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4.5 text-[14px] leading-relaxed text-amber-950">
                <strong>ขอบเขตการใช้งาน:</strong> ใช้สำรวจระดับความเสี่ยงพอร์ตเท่านั้น <strong>ไม่ใช่คำแนะนำการลงทุน</strong> เป้าหมายกำไร หรือจุด Stop-loss
              </div>
            </div>

            <div className="col-span-7 h-full">
              <PortfolioBudgetLab weightsB={weightsB} portfolioRows={portfolioRows} />
            </div>
          </div>
        </SlideFrame>
  );
}
