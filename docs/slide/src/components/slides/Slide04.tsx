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

export function Slide04() {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(4);
  return (
        <SlideFrame
          slideNumber={4}
          totalSlides={total}
          title={SLIDE_TITLES[3]}
          subtitle="รวบรวม ตรวจสอบ Data Contract และแยก Features/Labels เพื่อกันข้อมูลอนาคตรั่วไหล"
          showSourceFooter={showFooter}
        >
          <div className="grid flex-1 grid-cols-12 gap-6 py-2">
            <div className="col-span-5 flex h-full flex-col justify-between gap-4">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/55 p-5">
                <div className="text-[15px] font-bold text-emerald-900">
                  ผลการตรวจคุณภาพชุดข้อมูลหลัก
                </div>
                <div className="font-mono-num mt-3 grid grid-cols-2 gap-2.5 text-[13.5px]">
                  <div className="rounded-lg bg-white px-3.5 py-2.5">
                    <span className="text-zinc-500">รวมทั้งหมด:</span> <strong>3,948 แถว</strong>
                  </div>
                  <div className="rounded-lg bg-white px-3.5 py-2.5">
                    <span className="text-zinc-500">วันขาด / กักกัน:</span> <strong className="text-emerald-700">0 / 0</strong>
                  </div>
                  <div className="col-span-2 rounded-lg bg-white px-3.5 py-2.5">
                    <span className="text-zinc-500">ตรวจสูตรความผันผวน (3 หน้าต่าง × 3 ETF):</span> <strong className="text-emerald-700">ผ่าน 9/9 คู่</strong>
                  </div>
                </div>
              </div>

              <div className="flex flex-1 flex-col justify-center overflow-hidden rounded-xl border border-zinc-200 bg-white">
                <table className="w-full text-left text-[13.5px]">
                  <thead className="border-b border-zinc-200 bg-zinc-100 text-zinc-700">
                    <tr>
                      <th className="px-4 py-3 font-bold">ETF</th>
                      <th className="px-4 py-3 font-bold">Yahoo Raw</th>
                      <th className="px-4 py-3 font-bold">แหล่งอิสระ (100 วันแรง)</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono-num divide-y divide-zinc-200">
                    <tr>
                      <td className="px-4 py-3 font-bold text-[#9E0B0F]">SPY</td>
                      <td className="px-4 py-3">100 / 100</td>
                      <td className="px-4 py-3">100 / 100 (Tiingo)</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-bold text-blue-700">IEF</td>
                      <td className="px-4 py-3">100 / 100</td>
                      <td className="px-4 py-3">100 / 100 (Tiingo)</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-bold text-amber-700">GLD</td>
                      <td className="px-4 py-3">100 / 100</td>
                      <td className="px-4 py-3">100 / 100 (SPDR ถึงระดับเซนต์)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div className="col-span-7 h-full">
              <UnifiedPipelineDiagram />
            </div>
          </div>
        </SlideFrame>
  );
}
