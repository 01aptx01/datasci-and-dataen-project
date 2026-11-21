import React from 'react';
import {
  ChevronLeft,
  ChevronRight,
  FileDown,
  FileText,
  LayoutGrid,
  Maximize,
  MessageSquareText,
  Minimize,
} from 'lucide-react';
import { SlideRenderer, SLIDE_REGISTRY } from './components/Slides';
import { PresentationStage } from './components/PresentationStage';
import { usePresentationData } from './hooks/usePresentationData';
import { usePresentationControls } from './hooks/usePresentationControls';

const TOTAL_SLIDES = SLIDE_REGISTRY.length;

export default function App() {
  const data = usePresentationData();
  const controls = usePresentationControls(TOTAL_SLIDES);
  const { currentSlide, isFullscreen, isGridOpen, setIsGridOpen, isScrollMode, setIsScrollMode, isNotesOpen, setIsNotesOpen, setIsEvidenceOpen, appRootRef, goToSlide, nextSlide, prevSlide, toggleFullscreen, handleExportPdf } = controls;

  const dockBtnBase =
    'flex h-8 w-8 cursor-pointer items-center justify-center rounded-full bg-zinc-700/80 text-zinc-100 transition-colors hover:bg-zinc-600 disabled:cursor-not-allowed disabled:opacity-35';

  const sharedSlideProps = {
    onGoToSlide: goToSlide,
    onOpenEvidence: () => setIsEvidenceOpen(true),
    weightsB: data.weightsB,
    onChangeWeightsB: data.setWeightsB,
    savedReplayRows: data.savedReplayRows,
    savedReplayFileName: data.savedReplayFileName,
    onUploadSavedReplay: data.handleUploadSavedReplay,
    onClearSavedReplay: data.handleClearSavedReplay,
    portfolioRows: data.portfolioRows,
    portfolioFileName: data.portfolioFileName,
    selectedCsvDateIdx: data.selectedCsvDateIdx,
    onChangeCsvDateIdx: data.setSelectedCsvDateIdx,
    onUploadPortfolioCsv: data.handleUploadPortfolioCsv,
    onClearPortfolioCsv: data.handleClearPortfolioCsv,
    driftRows: data.driftRows,
    driftFileName: data.driftFileName,
    onUploadDrift: data.handleUploadDrift,
    onClearDrift: data.handleClearDrift,
    h1ScatterRows: data.h1ScatterRows,
  };

  return (
    <>
      {/* Screen Presentation Shell */}
      <div
        ref={appRootRef}
        className={`no-print relative flex h-screen w-screen flex-col overflow-hidden transition-colors ${
          isFullscreen ? 'bg-zinc-950 text-white' : 'bg-zinc-100 text-zinc-900'
        }`}
      >
        {data.loadErrors.length > 0 && (
          <div role="alert" className="absolute top-3 right-3 z-50 max-w-md rounded-lg border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-900 shadow">
            โหลดข้อมูลสไลด์ไม่ครบ: {data.loadErrors.join(' · ')}
          </div>
        )}
        {/* Main Stage */}
        <PresentationStage controls={controls} slideProps={sharedSlideProps} />

        {/* Floating Compact Dark Pill Dock */}
        <nav
          aria-label="แถบควบคุมสไลด์"
          className="fixed bottom-3 left-1/2 z-30 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-zinc-700/80 bg-zinc-800/95 px-2 py-1.5 shadow-2xl backdrop-blur-md"
        >
          <button
            type="button"
            onClick={prevSlide}
            disabled={currentSlide === 1 || isScrollMode}
            title="สไลด์ก่อนหน้า"
            aria-label="สไลด์ก่อนหน้า"
            className={dockBtnBase}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={() => setIsGridOpen((prev) => !prev)}
            title="เปิดสารบัญสไลด์"
            className="font-mono-num cursor-pointer px-2.5 text-[13px] font-medium whitespace-nowrap text-zinc-100 hover:text-white"
          >
            {currentSlide} / {TOTAL_SLIDES}
          </button>

          <button
            type="button"
            onClick={nextSlide}
            disabled={currentSlide === TOTAL_SLIDES || isScrollMode}
            title="สไลด์ถัดไป"
            aria-label="สไลด์ถัดไป"
            className={dockBtnBase}
          >
            <ChevronRight className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={() => setIsGridOpen((prev) => !prev)}
            title="ดูภาพรวมสไลด์ทั้งหมด"
            aria-label="ดูภาพรวมสไลด์ทั้งหมด"
            className={`${dockBtnBase} ${isGridOpen ? 'ring-2 ring-white/70' : ''}`}
          >
            <LayoutGrid className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={() => setIsNotesOpen((prev) => !prev)}
            title="สคริปต์ผู้บรรยาย (N)"
            aria-label="สคริปต์ผู้บรรยาย"
            className={`${dockBtnBase} ${isNotesOpen ? 'bg-[#9E0B0F] hover:bg-[#B81418]' : ''}`}
          >
            <MessageSquareText className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={toggleFullscreen}
            title={isFullscreen ? 'ย่อจอ' : 'เต็มจอ'}
            aria-label={isFullscreen ? 'ย่อจอ' : 'เต็มจอ'}
            className={dockBtnBase}
          >
            {isFullscreen ? (
              <Minimize className="h-4 w-4" />
            ) : (
              <Maximize className="h-4 w-4" />
            )}
          </button>

          <button
            type="button"
            onClick={() => setIsScrollMode((prev) => !prev)}
            title={isScrollMode ? 'กลับมุมมองทีละสไลด์' : 'ดูทุกสไลด์เรียงต่อกัน'}
            aria-label={isScrollMode ? 'กลับมุมมองทีละสไลด์' : 'ดูทุกสไลด์เรียงต่อกัน'}
            className={`${dockBtnBase} ${isScrollMode ? 'bg-[#9E0B0F] hover:bg-[#B81418]' : ''}`}
          >
            <FileText className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={handleExportPdf}
            title="ส่งออกเป็น PDF 16:9"
            aria-label="ส่งออกเป็น PDF 16:9"
            className={dockBtnBase}
          >
            <FileDown className="h-4 w-4" />
          </button>
        </nav>
      </div>

      {/* Dedicated 16:9 Print Container */}
      <div className="print-deck hidden">
        {SLIDE_REGISTRY.map((_, idx) => (
          <div key={idx} className="print-slide-page">
            <div className="print-slide-scaler">
              <SlideRenderer slideNumber={idx + 1} {...sharedSlideProps} />
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
