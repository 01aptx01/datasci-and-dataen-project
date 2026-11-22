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

export function Slide11() {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(11);
  return (
        <SlideFrame
          slideNumber={11}
          totalSlides={total}
          title={SLIDE_TITLES[10]}
          subtitle="รวมค่าพยากรณ์รายตัวกับสหสัมพันธ์ย้อนหลัง 20 วัน และน้ำหนักพอร์ตที่เลือก"
          showSourceFooter={showFooter}
        >
          <div className="grid flex-1 grid-cols-12 gap-6 py-2">
            <div className="col-span-6 flex h-full flex-col justify-between gap-4">
              <MathBox
                formula={
                  <>
                    <span>Σ = D · R</span>
                    <sub className="text-[12px]">20</sub>
                    <span>· D &nbsp;&nbsp;|&nbsp;&nbsp; σ</span>
                    <sub className="text-[12px]">พอร์ต</sub>
                    <span>=</span>
                    <Radical>
                      <span>
                        w<sup>T</sup> Σ w
                      </span>
                    </Radical>
                  </>
                }
                explanationTh="D คือความผันผวนพยากรณ์ราย ETF (B3), R₂₀ คือสหสัมพันธ์ย้อนหลัง 20 วัน และ w คือน้ำหนักของทั้ง 3 กองทุน"
              />

              <div className="flex flex-1 flex-col justify-center rounded-xl border border-emerald-200 bg-emerald-50/50 p-6 text-[15.5px] text-emerald-950">
                <div className="text-[18px] font-bold">ชุด Test พร้อมคำนวณ 248 วัน (สถานะ OK 100%)</div>
                <p className="mt-2.5 leading-relaxed text-emerald-900">
                  เมื่อผู้ใช้เปลี่ยนสัดส่วนน้ำหนักพอร์ต w ระบบคำนวณความเสี่ยงพอร์ตใหม่จากเมทริกซ์ Σ เดิมได้ทันที โดยไม่ต้องฝึกโมเดลใหม่
                </p>
              </div>
            </div>

            <div className="col-span-6 h-full">
              <PortfolioBridgeSteps />
            </div>
          </div>
        </SlideFrame>
  );
}
