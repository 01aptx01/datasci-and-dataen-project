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

export function Slide15({ onOpenEvidence }: SlideContextProps) {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(15);
  return (
        <SlideFrame
          slideNumber={15}
          totalSlides={total}
          title={SLIDE_TITLES[14]}
          subtitle="สรุปแกนหลักทั้ง 3 ด้าน แนวทางพัฒนาต่อ และรหัสอ้างอิงการทดลอง"
          showSourceFooter={showFooter}
        >
          <div className="flex flex-1 flex-col justify-between gap-4 py-2">
            <div className="grid flex-1 grid-cols-3 gap-4">
              <div className="flex flex-col justify-center rounded-xl border border-zinc-200 bg-white p-6">
                <div className="text-[13.5px] font-bold text-[#9E0B0F]">1. ด้าน Data Engineering</div>
                <div className="font-display mt-1.5 text-[20px] font-bold text-zinc-900">
                  Pipeline ตรวจสอบย้อนกลับได้
                </div>
                <p className="mt-2.5 text-[15px] leading-relaxed text-zinc-700">
                  ข้อมูล XNYS 3,948 แถว ขาด 0 กักกัน 0 แยก Features/Labels ชัดเจน พร้อมเทียบแหล่งอิสระ 100/100
                </p>
              </div>

              <div className="flex flex-col justify-center rounded-xl border border-[#9E0B0F]/35 bg-red-50/35 p-6">
                <div className="text-[13.5px] font-bold text-[#9E0B0F]">2. ด้าน Data Science</div>
                <div className="font-display mt-1.5 text-[20px] font-bold text-zinc-900">
                  Online SGD (B3) Error ต่ำสุด
                </div>
                <p className="mt-2.5 text-[15px] leading-relaxed text-zinc-700">
                  Macro MAE 0.048892 ดีกว่า B2 6.83% และ B1 17.61% (H2, H3 adj. p &lt; 0.01) พร้อม ADWIN 0 Alerts
                </p>
              </div>

              <div className="flex flex-col justify-center rounded-xl border border-zinc-200 bg-white p-6">
                <div className="text-[13.5px] font-bold text-[#9E0B0F]">3. ด้าน Portfolio Risk Lab</div>
                <div className="font-display mt-1.5 text-[20px] font-bold text-zinc-900">
                  ปรับน้ำหนักพอร์ตได้ทันที
                </div>
                <p className="mt-2.5 text-[15px] leading-relaxed text-zinc-700">
                  248 วัน Test สถานะ OK ครบ 100% เทียบ Scenario A/B และงบความผันผวนได้โดยไม่ต้องฝึกโมเดลใหม่
                </p>
              </div>
            </div>

            <div className="grid grid-cols-12 gap-4">
              <div className="col-span-8 rounded-xl border border-zinc-200 bg-zinc-50 p-5">
                <div className="text-[15px] font-bold text-zinc-900">ก้าวถัดไป (Next Steps)</div>
                <div className="mt-2.5 grid grid-cols-3 gap-4 text-[14px] text-zinc-700">
                  <div>• <strong>ตรวจ Point-in-Time:</strong> ทดสอบกับข้อมูลจริงรายวันแบบ Live</div>
                  <div>• <strong>ขยายสินทรัพย์/ช่วงเวลา:</strong> ทดสอบนอกเหนือ 3 ETF และหลายสภาวะ</div>
                  <div>• <strong>Dashboard D3–D7:</strong> พัฒนาเครื่องมือวิเคราะห์ต่อจาก D1–D2</div>
                </div>
              </div>

              <div className="no-print col-span-4 flex items-center justify-center rounded-xl border border-[#9E0B0F]/30 bg-red-50/40 p-5">
                {onOpenEvidence ? (
                  <button
                    type="button"
                    onClick={onOpenEvidence}
                    className="w-full cursor-pointer rounded-xl bg-[#9E0B0F] px-4 py-3.5 text-[15px] font-bold text-white shadow-sm transition-colors hover:bg-[#B81418]"
                  >
                    เปิดดูหลักฐานอ้างอิง (Eval &amp; Replay ID)
                  </button>
                ) : (
                  <div className="font-mono-num text-[12.5px] text-zinc-700">
                    Eval: {EXPERIMENT_IDENTITY.evalId.slice(0, 12)}...
                  </div>
                )}
              </div>
            </div>
          </div>
        </SlideFrame>
  );
}
