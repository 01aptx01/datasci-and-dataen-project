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

export function Slide01() {
  const total = SLIDE_TITLES.length;
  return (
        <SlideFrame slideNumber={1} totalSlides={total} isCover>
          <div className="flex h-full flex-col justify-between px-[72px] pt-[92px] pb-[32px]">
            <div className="max-w-[585px]">
              <h1 className="font-display text-[50px] leading-[1.2] font-bold tracking-[-0.015em] text-[#9E0B0F] [text-wrap:balance]">
                {COURSE_INFO.projectTitleLine1}
                <br />
                <span className="text-zinc-900">{COURSE_INFO.projectTitleLine2}</span>
              </h1>
              <p className="font-display mt-5 text-[24px] font-medium text-zinc-700">
                {COURSE_INFO.subtitle}
              </p>

              <div className="mt-10 rounded-xl border border-zinc-200/90 bg-white/90 px-6 py-5 backdrop-blur-xs">
                <div className="text-[14px] font-bold text-[#9E0B0F]">
                  {COURSE_INFO.course} · {COURSE_INFO.academicYear}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 text-[14.5px] text-zinc-800">
                  {TEAM_MEMBERS.map((m) => (
                    <div key={m.studentId} className="flex items-center justify-between gap-2">
                      <span>
                        {m.index}. {m.name}
                      </span>
                      <span className="font-mono-num text-[13px] text-zinc-500">
                        {m.studentId}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between text-[14.5px] font-medium text-zinc-700">
              <span>พยากรณ์ความผันผวนรายสินทรัพย์ SPY · IEF · GLD ด้วยข้อมูลรายวัน 5 ปี</span>
            </div>
          </div>
        </SlideFrame>
  );
}
