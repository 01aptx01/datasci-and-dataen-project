import React from 'react';
import { PRESENTER_NOTES, RESULT_SLIDES, SLIDE_TITLES } from '../data/reportData';
import type { DriftTimelineRow, H1ScatterRow, PortfolioRiskRow, SavedReplayRow } from '../utils/stage06Csv';
import { Slide01 } from './slides/Slide01';
import { Slide02 } from './slides/Slide02';
import { Slide03 } from './slides/Slide03';
import { Slide04 } from './slides/Slide04';
import { Slide05 } from './slides/Slide05';
import { Slide06 } from './slides/Slide06';
import { Slide07 } from './slides/Slide07';
import { Slide08 } from './slides/Slide08';
import { Slide09 } from './slides/Slide09';
import { Slide10 } from './slides/Slide10';
import { Slide11 } from './slides/Slide11';
import { Slide12 } from './slides/Slide12';
import { Slide13 } from './slides/Slide13';
import { Slide14 } from './slides/Slide14';
import { Slide15 } from './slides/Slide15';

export interface SlideDeckProps {
  slideNumber: number;
  onGoToSlide?: (n: number) => void;
  onOpenEvidence?: () => void;
  weightsB: { SPY: number; IEF: number; GLD: number };
  onChangeWeightsB: (w: { SPY: number; IEF: number; GLD: number }) => void;
  savedReplayRows: SavedReplayRow[] | null;
  savedReplayFileName: string | null;
  onUploadSavedReplay: (rows: SavedReplayRow[], name: string) => void;
  onClearSavedReplay: () => void;
  portfolioRows: PortfolioRiskRow[] | null;
  portfolioFileName: string | null;
  selectedCsvDateIdx: number;
  onChangeCsvDateIdx: (idx: number) => void;
  onUploadPortfolioCsv: (rows: PortfolioRiskRow[], name: string) => void;
  onClearPortfolioCsv: () => void;
  driftRows: DriftTimelineRow[] | null;
  driftFileName: string | null;
  onUploadDrift: (rows: DriftTimelineRow[], name: string) => void;
  onClearDrift: () => void;
  h1ScatterRows: H1ScatterRow[];
}

export type SlideContextProps = Omit<SlideDeckProps, 'slideNumber'>;

const slideComponents = [
  Slide01,
  Slide02,
  Slide03,
  Slide04,
  Slide05,
  Slide06,
  Slide07,
  Slide08,
  Slide09,
  Slide10,
  Slide11,
  Slide12,
  Slide13,
  Slide14,
  Slide15,
] as const;

export const SLIDE_REGISTRY = slideComponents.map((Component, index) => ({
  number: index + 1,
  title: SLIDE_TITLES[index],
  notes: PRESENTER_NOTES[index],
  hasResultFooter: RESULT_SLIDES.has(index + 1),
  Component,
}));

export function SlideRenderer({ slideNumber, ...props }: SlideDeckProps) {
  const Component = SLIDE_REGISTRY[slideNumber - 1]?.Component ?? Slide15;
  return <Component {...props} />;
}
