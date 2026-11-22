import React from 'react';
import { Clock, MessageSquareText, X } from 'lucide-react';
import { EXPERIMENT_IDENTITY } from '../data/reportData';
import { SLIDE_HEIGHT, SLIDE_WIDTH } from '../presentationLayout';
import { SlideRenderer, SLIDE_REGISTRY, type SlideContextProps } from './Slides';
import type { usePresentationControls } from '../hooks/usePresentationControls';

type Controls = ReturnType<typeof usePresentationControls>;

export function PresentationStage({ controls, slideProps }: { controls: Controls; slideProps: SlideContextProps }) {
  const { currentSlide, isFullscreen, isScrollMode, isNotesOpen, setIsNotesOpen, isGridOpen, setIsGridOpen, isEvidenceOpen, setIsEvidenceOpen, scale, stageContainerRef, goToSlide } = controls;
  const TOTAL_SLIDES = SLIDE_REGISTRY.length;
  const currentNote = SLIDE_REGISTRY[currentSlide - 1]?.notes ?? SLIDE_REGISTRY[0].notes;
  const sharedSlideProps = slideProps;
  return (        <main
          ref={stageContainerRef}
          className={`relative flex-1 ${
            isScrollMode
              ? 'overflow-y-auto px-6 pt-6 pb-20'
              : isFullscreen
              ? 'flex items-center justify-center overflow-hidden p-3'
              : 'flex items-center justify-center overflow-hidden pb-16'
          }`}
        >
          {isScrollMode ? (
            <div className="mx-auto flex flex-col items-center gap-6 pb-8">
              {SLIDE_REGISTRY.map((_, idx) => {
                const num = idx + 1;
                const scrollScale = Math.min(scale, 0.78);
                return (
                  <div key={num} className="flex flex-col items-center gap-1.5">
                    <div
                      onClick={() => goToSlide(num)}
                      className="cursor-pointer rounded-sm transition-transform hover:scale-[1.005]"
                      style={{
                        width: SLIDE_WIDTH * scrollScale,
                        height: SLIDE_HEIGHT * scrollScale,
                      }}
                      title={`คลิกเพื่อเปิดสไลด์หน้า ${num}`}
                    >
                      <div
                        className="origin-top-left"
                        style={{
                          width: SLIDE_WIDTH,
                          height: SLIDE_HEIGHT,
                          transform: `scale(${scrollScale})`,
                        }}
                      >
                        <SlideRenderer slideNumber={num} {...sharedSlideProps} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div
              style={{
                width: SLIDE_WIDTH * scale,
                height: SLIDE_HEIGHT * scale,
              }}
              className="relative shrink-0"
            >
              <div
                className="origin-top-left"
                style={{
                  width: SLIDE_WIDTH,
                  height: SLIDE_HEIGHT,
                  transform: `scale(${scale})`,
                }}
              >
                <div key={currentSlide} className="slide-enter h-full w-full">
                  <SlideRenderer slideNumber={currentSlide} {...sharedSlideProps} />
                </div>
              </div>
            </div>
          )}

          {/* Presenter Notes Floating Drawer (Thai Cue Script) */}
          {isNotesOpen && !isScrollMode && (
            <aside
              aria-label="สคริปต์ผู้บรรยาย"
              className="fixed right-5 bottom-20 z-35 w-[390px] max-w-[calc(100vw-2.5rem)] rounded-2xl border border-zinc-700/80 bg-zinc-900/95 p-4 text-zinc-100 shadow-2xl backdrop-blur-md"
            >
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5">
                <div className="flex items-center gap-2">
                  <MessageSquareText className="h-4 w-4 text-red-400" />
                  <span className="font-display text-[14px] font-bold">
                    สคริปต์ผู้บรรยาย · หน้า {currentSlide}/{TOTAL_SLIDES}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono-num inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-0.5 text-[11.5px] text-zinc-300">
                    <Clock className="h-3 w-3" />
                    {currentNote.duration}
                  </span>
                  <button
                    type="button"
                    onClick={() => setIsNotesOpen(false)}
                    aria-label="ปิดสคริปต์ผู้บรรยาย"
                    className="cursor-pointer rounded-full p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <ul className="mt-3 flex flex-col gap-2 text-[13px] leading-relaxed text-zinc-200">
                {currentNote.talkingPoints.map((pt, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="font-mono-num text-red-400">•</span>
                    <span>{pt}</span>
                  </li>
                ))}
              </ul>

              <div className="mt-3 border-t border-zinc-800 pt-2 text-[11.5px] text-zinc-400">
                อ้างอิง: {currentNote.sourceNote} (กด N เพื่อเปิด/ปิด)
              </div>
            </aside>
          )}

          {/* Grid Overview Modal */}
          {isGridOpen && (
            <div
              className="fixed inset-0 z-40 flex items-center justify-center bg-black/55 p-6 backdrop-blur-[2px]"
              onClick={() => setIsGridOpen(false)}
            >
              <div
                className="flex max-h-[82vh] w-full max-w-[920px] flex-col rounded-2xl border border-zinc-700 bg-zinc-900 p-5 text-white shadow-2xl"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                  <h2 className="font-display text-[17px] font-bold">
                    ภาพรวมสไลด์ทั้งหมด ({TOTAL_SLIDES} หน้า)
                  </h2>
                  <button
                    type="button"
                    onClick={() => setIsGridOpen(false)}
                    aria-label="ปิดหน้าต่างสารบัญ"
                    className="cursor-pointer rounded-full p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-2.5 overflow-y-auto pr-1 sm:grid-cols-2 lg:grid-cols-3">
                  {SLIDE_REGISTRY.map(({ title }, idx) => {
                    const num = idx + 1;
                    const active = num === currentSlide && !isScrollMode;
                    return (
                      <button
                        key={num}
                        type="button"
                        onClick={() => goToSlide(num)}
                        className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 text-left transition-all ${
                          active
                            ? 'border-[#9E0B0F] bg-[#9E0B0F]/20 text-white'
                            : 'border-zinc-800 bg-zinc-800/70 text-zinc-200 hover:border-zinc-600 hover:bg-zinc-800'
                        }`}
                      >
                        <span
                          className={`font-mono-num flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[12px] font-bold ${
                            active
                              ? 'bg-[#9E0B0F] text-white'
                              : 'bg-zinc-700 text-zinc-200'
                          }`}
                        >
                          {num}
                        </span>
                        <span className="text-[13.5px] leading-snug font-medium">
                          {title}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Evidence & Experiment Identity Modal (Triggered from Slide 15) */}
          {isEvidenceOpen && (
            <div
              className="fixed inset-0 z-45 flex items-center justify-center bg-black/60 p-6 backdrop-blur-[2px]"
              onClick={() => setIsEvidenceOpen(false)}
            >
              <div
                className="w-full max-w-[680px] rounded-2xl border border-zinc-700 bg-zinc-900 p-6 text-zinc-100 shadow-2xl"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                  <h2 className="font-display text-[17px] font-bold text-white">
                    หลักฐานอ้างอิงและรหัสกำกับการทดลอง (Report บทที่ 1–11)
                  </h2>
                  <button
                    type="button"
                    onClick={() => setIsEvidenceOpen(false)}
                    aria-label="ปิดหน้าต่างหลักฐานอ้างอิง"
                    className="cursor-pointer rounded-full p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <div className="mt-4 flex flex-col gap-3 text-[13px]">
                  <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3.5">
                    <div className="text-zinc-400">Frozen Evaluation ID</div>
                    <div className="font-mono-num mt-0.5 break-all text-zinc-100">
                      {EXPERIMENT_IDENTITY.evalId}
                    </div>
                  </div>

                  <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3.5">
                    <div className="text-zinc-400">Saved Replay ID</div>
                    <div className="font-mono-num mt-0.5 break-all text-zinc-100">
                      {EXPERIMENT_IDENTITY.replayId}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3">
                      <div className="text-zinc-400">Ingestion Run ID</div>
                      <div className="font-mono-num mt-0.5 text-zinc-100">
                        {EXPERIMENT_IDENTITY.ingestionRun}
                      </div>
                    </div>
                    <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3">
                      <div className="text-zinc-400">Feature Engineering Run</div>
                      <div className="font-mono-num mt-0.5 text-zinc-100">
                        {EXPERIMENT_IDENTITY.featureRun}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3.5 leading-relaxed text-zinc-300">
                    <div>
                      • <strong>ช่วงศึกษาทั้งหมด:</strong> {EXPERIMENT_IDENTITY.studyRange} (1,255 วันซื้อขาย/ETF + 61 วัน Warm-up)
                    </div>
                    <div>
                      • <strong>ช่วงชุด Test (ตัดรอบข้อมูล):</strong> {EXPERIMENT_IDENTITY.testRange} (Cutoff: {EXPERIMENT_IDENTITY.dataCutoff})
                    </div>
                    <div>
                      • <strong>ขอบเขตอ้างอิง:</strong> ตัวเลขทั้งหมดอ้างอิงจากรายงาน CSS 342 บทที่ 1–11 เท่านั้น
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
  );
}
