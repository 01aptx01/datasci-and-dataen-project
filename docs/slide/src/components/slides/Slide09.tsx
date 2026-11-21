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

export function Slide09({ driftRows, driftFileName, onUploadDrift, onClearDrift }: SlideContextProps) {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(9);
  return (
        <SlideFrame
          slideNumber={9}
          totalSlides={total}
          title={SLIDE_TITLES[8]}
          subtitle="วงจร Predict-then-Evaluate 6 ขั้นรายวัน พร้อม ADWIN เฝ้าระวัง"
          showSourceFooter={showFooter}
        >
          <div className="grid flex-1 grid-cols-12 gap-6 py-2">
            <div className="col-span-5 flex h-full flex-col justify-between gap-4">
              <div className="flex flex-1 flex-col justify-center rounded-xl border border-zinc-200 bg-white p-5.5">
                <h3 className="font-display text-[19px] font-bold text-[#9E0B0F]">
                  เหตุใด B3 จึงปรับตัวดีกว่า B2?
                </h3>
                <p className="mt-3 text-[15.5px] leading-relaxed text-zinc-800">
                  B2 ตรึงน้ำหนักไว้หลังจบช่วง Train จึงปรับตัวเมื่อตลาดเปลี่ยนไม่ได้ แต่ B3 อัปเดตเพิ่มเมื่อ Label เดิมครบ 5 วัน (Mature) ทำให้รับรู้สภาวะความผันผวนล่าสุดโดยไม่รั่วไหล
                </p>
              </div>

              <div className="flex flex-1 flex-col justify-center rounded-xl border border-zinc-200 bg-zinc-50 p-5.5 text-[15px] leading-snug text-zinc-800">
                <div className="text-[16px] font-bold text-zinc-900">กติกาของ ADWIN (delta = 0.002)</div>
                <ul className="mt-2.5 flex flex-col gap-2">
                  <li>• เฝ้าระวังความคลาดเคลื่อนเท่านั้น <strong>(Monitor-only)</strong></li>
                  <li>• ไม่สั่ง Reset หรือ Retrain โมเดลอัตโนมัติ</li>
                  <li>• บันทึก Checkpoint Hash ทุกวันเพื่อตรวจซ้ำได้</li>
                </ul>
              </div>
            </div>

            <div className="col-span-7 h-full">
              <OnlineSgdMonitoringLab
                driftRows={driftRows}
                driftFileName={driftFileName}
                onUploadDrift={onUploadDrift}
                onClearDrift={onClearDrift}
              />
            </div>
          </div>
        </SlideFrame>
  );
}
