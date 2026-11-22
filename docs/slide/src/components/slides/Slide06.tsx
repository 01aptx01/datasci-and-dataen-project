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

export function Slide06() {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(6);
  return (
        <SlideFrame
          slideNumber={6}
          totalSlides={total}
          title={SLIDE_TITLES[5]}
          subtitle="เปรียบเทียบ B0–B3 บนชุดข้อมูลเดียวกัน (Train → Purge → Validation → Purge → Test)"
          showSourceFooter={showFooter}
        >
          <div className="flex flex-1 flex-col justify-between gap-4 py-2">
            <ModelsAndSplitLab />

            <div className="grid grid-cols-3 gap-4 text-[14.5px]">
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-5 py-4 text-zinc-800">
                <div className="font-bold text-[#9E0B0F]">ฟีเจอร์หลัก 8 ตัว (B2 และ B3)</div>
                <div className="mt-1.5 text-zinc-600">
                  ผลตอบแทน 5 ตัว (วัน t, t-1, t-2, 5d, 20d) + ความผันผวนย้อนหลัง 3 ตัว (RV5, RV20, RV60)
                </div>
              </div>
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-5 py-4 text-zinc-800">
                <div className="font-bold text-zinc-900">จูนโมเดลบน Validation เท่านั้น</div>
                <div className="mt-1.5 text-zinc-600">
                  ฟิต <span className="font-mono-num">RobustScaler</span> บน Train และเลือกจาก 27 ชุด/ETF โดยไม่แตะ Test
                </div>
              </div>
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-5 py-4 text-zinc-800">
                <div className="font-bold text-zinc-900">ประเมินบน Common Panel เดียวกัน</div>
                <div className="mt-1.5 text-zinc-600">
                  วัดผลด้วย <span className="font-mono-num">Macro MAE</span> น้ำหนักเท่ากันทั้ง 3 ETF บน 729 คู่
                </div>
              </div>
            </div>
          </div>
        </SlideFrame>
  );
}
