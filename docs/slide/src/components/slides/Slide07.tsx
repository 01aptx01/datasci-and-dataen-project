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

export function Slide07({ savedReplayRows, savedReplayFileName, onUploadSavedReplay, onClearSavedReplay }: SlideContextProps) {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(7);
  return (
        <SlideFrame
          slideNumber={7}
          totalSlides={total}
          title={SLIDE_TITLES[6]}
          subtitle="ตรวจสอบยอดคำพยากรณ์ชุด Test พร้อมรองรับไฟล์ CSV รายวัน"
          showSourceFooter={showFooter}
        >
          <div className="flex flex-1 flex-col justify-between gap-3.5 py-2">
            <SavedReplayMiniLab
              rows={savedReplayRows}
              fileName={savedReplayFileName}
              onUploadRows={onUploadSavedReplay}
              onClearRows={onClearSavedReplay}
            />

            <div className="grid grid-cols-2 gap-4 text-[13px] text-zinc-700">
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4.5 py-3">
                <strong>Eval ID:</strong>{' '}
                <span className="font-mono-num text-zinc-600">
                  {EXPERIMENT_IDENTITY.evalId.slice(0, 20)}...
                </span>{' '}
                · <strong>Replay ID:</strong>{' '}
                <span className="font-mono-num text-zinc-600">
                  {EXPERIMENT_IDENTITY.replayId.slice(0, 20)}...
                </span>
              </div>
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4.5 py-3">
                <strong>กฎซ่อนค่า Pending:</strong> แถว <span className="font-mono-num font-bold text-amber-800">PENDING</span> (60 รายการปลายช่วง) ซ่อนค่าจริงและไม่นำไปคำนวณ Error
              </div>
            </div>
          </div>
        </SlideFrame>
  );
}
