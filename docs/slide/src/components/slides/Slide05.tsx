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

export function Slide05() {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(5);
  return (
        <SlideFrame
          slideNumber={5}
          totalSlides={total}
          title={SLIDE_TITLES[4]}
          subtitle="คำนวณจาก Log Return 5 วันซื้อขายข้างหน้า (t+1 ถึง t+5) แปลงเป็นหน่วยรายปี"
          showSourceFooter={showFooter}
        >
          <div className="grid flex-1 grid-cols-12 gap-6 py-2">
            <div className="col-span-5 flex h-full flex-col justify-between gap-4">
              <MathBox
                formula={
                  <>
                    <span>RV</span>
                    <sub className="mr-1 text-[12px]">forward5</sub>
                    <span>(i, t) =</span>
                    <Radical>
                      <Fraction num="252" den="5" />
                      <span className="mx-1">×</span>
                      <Summation lower="k=1" upper="5" />
                      <span>
                        r<sub className="text-[12px]">i, t+k</sub>
                        <sup className="text-[12px]">2</sup>
                      </span>
                    </Radical>
                  </>
                }
                explanationTh="แปลงความผันผวนของ 5 วันข้างหน้าเป็นหน่วยต่อปี · เช่น 0.20 คือ 20% ต่อปีบนกรอบ 5 วัน"
              />

              <div className="flex flex-1 flex-col justify-center rounded-xl border border-zinc-200 bg-white p-5 text-[15px] leading-relaxed text-zinc-800">
                <div className="text-[16px] font-bold text-[#9E0B0F]">กฎ Label Maturity Gate</div>
                <ul className="mt-3 flex flex-col gap-2.5">
                  <li>• <strong>Pending:</strong> ก่อนวัน <span className="font-mono-num">t+5</span> ห้ามดูค่าจริงหรือสอน B3</li>
                  <li>• <strong>Mature:</strong> ครบ <span className="font-mono-num">target_end_date</span> จึงประเมินและอัปเดต B3</li>
                </ul>
              </div>
            </div>

            <div className="col-span-7 h-full">
              <MaturityTimelineWidget />
            </div>
          </div>
        </SlideFrame>
  );
}
