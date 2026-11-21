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

export function Slide12({ weightsB, onChangeWeightsB, portfolioRows, portfolioFileName, selectedCsvDateIdx, onChangeCsvDateIdx, onUploadPortfolioCsv, onClearPortfolioCsv }: SlideContextProps) {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(12);
  return (
        <SlideFrame
          slideNumber={12}
          totalSlides={total}
          title={SLIDE_TITLES[11]}
          subtitle="เทียบ Scenario A (50/30/20) กับ Scenario B พร้อมกราฟ Signed Risk Contributions"
          showSourceFooter={showFooter}
        >
          <div className="flex flex-1 flex-col justify-between gap-2.5 py-1">
            <div className="grid grid-cols-3 gap-3 text-[12.5px]">
              {PORTFOLIO_PRESETS.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between rounded-lg border border-zinc-200 bg-zinc-50 px-3.5 py-2"
                >
                  <span className="font-semibold text-zinc-700">ผลทดสอบ {p.id}:</span>
                  <span className="font-mono-num font-bold text-[#9E0B0F]">
                    เฉลี่ย {p.meanPct.toFixed(2)}% (มัธยฐาน {p.medianPct.toFixed(2)}%)
                  </span>
                </div>
              ))}
            </div>

            <PortfolioScenarioLab
              weightsB={weightsB}
              onChangeWeightsB={onChangeWeightsB}
              portfolioRows={portfolioRows}
              portfolioFileName={portfolioFileName}
              selectedCsvDateIdx={selectedCsvDateIdx}
              onChangeCsvDateIdx={onChangeCsvDateIdx}
              onUploadPortfolioCsv={onUploadPortfolioCsv}
              onClearPortfolioCsv={onClearPortfolioCsv}
            />
          </div>
        </SlideFrame>
  );
}
