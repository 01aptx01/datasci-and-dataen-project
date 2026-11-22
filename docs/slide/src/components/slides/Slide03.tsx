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

export function Slide03() {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(3);
  return (
        <SlideFrame
          slideNumber={3}
          totalSlides={total}
          title={SLIDE_TITLES[2]}
          subtitle="สินทรัพย์ 3 กลุ่มหลัก (SPY · IEF · GLD) ในช่วงศึกษา 5 ปี และคำถามวิจัย"
          showSourceFooter={showFooter}
        >
          <div className="grid flex-1 grid-cols-12 gap-6 py-2">
            <div className="col-span-5 flex h-full flex-col justify-between gap-4">
              <div className="flex flex-1 flex-col justify-center rounded-xl border border-red-200 bg-red-50/45 p-5.5">
                <div className="text-[13.5px] font-bold text-[#9E0B0F]">คำถามวิจัยหลัก</div>
                <p className="mt-2 text-[19px] leading-snug font-bold text-zinc-900">
                  การอัปเดตโมเดลแบบ Online (B3) ลด Error ได้ดีกว่าโมเดลที่ตรึงไว้ (B2) และเกณฑ์ฐาน RV20 (B1) หรือไม่?
                </p>
              </div>

              <div className="flex flex-1 flex-col justify-center rounded-xl border border-zinc-200 bg-white p-5.5 text-[15px] leading-snug text-zinc-800">
                <div className="text-[16px] font-bold text-zinc-900">ข้อสังเกต EDA ตลอด 5 ปี</div>
                <ul className="mt-3 flex flex-col gap-2.5">
                  <li>• ปี 2022 แกว่งตัวสลับขั้ว: <strong>SPY 24.26%</strong> สูงกว่า GLD (15.27%)</li>
                  <li>• หากตัดวันสุดขั้ว 5 วัน SD ลดลง ~7% (SPY / GLD)</li>
                  <li>• สหสัมพันธ์เฉลี่ย: SPY–IEF 0.10 · SPY–GLD 0.15 · IEF–GLD 0.30</li>
                </ul>
              </div>
            </div>

            <div className="col-span-7 h-full">
              <EtfUniverseInteractive />
            </div>
          </div>
        </SlideFrame>
  );
}
