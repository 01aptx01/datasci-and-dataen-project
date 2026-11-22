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

export function Slide08() {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(8);
  return (
        <SlideFrame
          slideNumber={8}
          totalSlides={total}
          title={SLIDE_TITLES[7]}
          subtitle="เปรียบเทียบ Error บนชุด Test (243 วัน/ETF · 729 คู่ · ค่ายิ่งต่ำยิ่งดี)"
          showSourceFooter={showFooter}
        >
          <div className="grid flex-1 grid-cols-12 gap-6 py-2">
            <div className="col-span-5 flex h-full flex-col justify-between gap-4">
              <div className="rounded-xl border border-zinc-200 bg-white p-5">
                <div className="text-[15.5px] font-bold text-zinc-900">
                  Macro MAE บนชุด Test
                </div>
                <div className="mt-3 flex flex-col gap-2.5">
                  {MODEL_METRICS_TEST.map((m) => {
                    const isB3 = m.id === 'B3';
                    return (
                      <div
                        key={m.id}
                        className={`flex items-center justify-between rounded-lg px-3.5 py-2.5 ${
                          isB3 ? 'border border-[#9E0B0F] bg-red-50/60' : 'bg-zinc-50'
                        }`}
                      >
                        <span className={`text-[14.5px] font-semibold ${isB3 ? 'text-[#9E0B0F]' : 'text-zinc-800'}`}>
                          {m.name}
                        </span>
                        <span className={`font-mono-num text-[16px] font-bold ${isB3 ? 'text-[#9E0B0F]' : 'text-zinc-900'}`}>
                          {m.mae.Macro.toFixed(6)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="flex flex-1 flex-col justify-center rounded-xl border border-zinc-200 bg-zinc-50 p-4.5 text-[14.5px] leading-relaxed text-zinc-800">
                <div>• B3 ลด Error จาก <strong className="text-[#9E0B0F]">B2 ได้ 6.83%</strong> และจาก <strong className="text-[#9E0B0F]">B1 ได้ 17.61%</strong></div>
                <div className="mt-1.5">• ทำนายสำเร็จ <strong>100% (2,976/2,976)</strong> · ประเมินได้ 97.98%</div>
                <div className="mt-1.5 text-zinc-500">• GLD มี Error สูงสุดในทุกโมเดล</div>
              </div>
            </div>

            <div className="col-span-7 h-full">
              <ModelMaeChart />
            </div>
          </div>
        </SlideFrame>
  );
}
