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

export function Slide14() {
  const total = SLIDE_TITLES.length;
  const showFooter = RESULT_SLIDES.has(14);
  return (
        <SlideFrame
          slideNumber={14}
          totalSlides={total}
          title={SLIDE_TITLES[13]}
          subtitle="ขอบเขตและข้อจำกัดของผลการศึกษา (รายงานบทที่ 10)"
          showSourceFooter={showFooter}
        >
          <div className="flex flex-1 flex-col py-2">
            <LimitationsStaticGrid />
          </div>
        </SlideFrame>
  );
}
