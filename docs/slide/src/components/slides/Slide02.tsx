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

export function Slide02() {
  const total = SLIDE_TITLES.length;
  return (
        <SlideFrame
          slideNumber={2}
          totalSlides={total}
          title={SLIDE_TITLES[1]}
          subtitle="แยกขนาดความแกว่งตัว (Volatility) ออกจากการทายทิศทางราคา (Return)"
        >
          <div className="grid flex-1 grid-cols-12 gap-6 py-2">
            <div className="col-span-7 h-full">
              <ReturnVsVolToggle />
            </div>

            <div className="col-span-5 flex h-full flex-col justify-between gap-4">
              <div className="flex flex-1 flex-col justify-center rounded-xl border border-zinc-200 bg-zinc-50 p-6">
                <h3 className="font-display text-[19px] font-bold text-[#9E0B0F]">
                  ขอบเขตและกติกาของโครงงาน
                </h3>
                <ul className="mt-4 flex flex-col gap-3.5 text-[16px] leading-snug text-zinc-800">
                  <li>• ใช้ราคาปิดปรับย้อนหลังรายวันตามปฏิทิน XNYS</li>
                  <li>• แยกขั้นตอน Features และ Labels ป้องกันข้อมูลรั่วไหล</li>
                  <li>• ใช้ประเมินความเสี่ยงพอร์ต ไม่ใช่คำแนะนำการลงทุน</li>
                </ul>
              </div>

              <div className="rounded-xl border border-zinc-200 bg-white px-5 py-4.5 text-[15.5px] leading-snug text-zinc-700">
                <strong>เป้าหมายทางวิศวกรรม:</strong> ปรับสัดส่วนพอร์ตได้ทันทีโดยไม่ต้องฝึกโมเดลใหม่ทุกครั้ง
              </div>
            </div>
          </div>
        </SlideFrame>
  );
}
