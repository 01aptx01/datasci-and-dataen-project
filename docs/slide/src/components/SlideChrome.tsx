import React from 'react';

interface SlideFrameProps {
  slideNumber: number;
  totalSlides: number;
  title?: string;
  subtitle?: string;
  isCover?: boolean;
  showSourceFooter?: boolean;
  children: React.ReactNode;
}

/**
 * Signature top-left layered deep crimson corner wave matching the reference slide deck (Slides 2–15).
 */
function TopLeftCrimsonWave() {
  return (
    <svg
      className="pointer-events-none absolute top-0 left-0 h-[112px] w-[230px]"
      viewBox="0 0 230 112"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M0 0 H226 C180 30 120 42 74 64 C38 82 18 96 0 112 V0 Z"
        fill="#B81418"
        opacity="0.92"
      />
      <path
        d="M0 0 H196 C152 26 98 38 56 58 C28 72 12 88 0 104 V0 Z"
        fill="#9E0B0F"
      />
      <path
        d="M0 0 H160 C120 22 72 32 38 50 C18 61 8 76 0 90 V0 Z"
        fill="#7A0508"
      />
    </svg>
  );
}

/**
 * Geometric polygonal white/light-gray cover background + 3D rising red bars & sweeping arrow (Slide 1).
 */
export function CoverDecorations() {
  return (
    <>
      {/* Subtle geometric polygonal background */}
      <svg
        className="pointer-events-none absolute inset-0 h-full w-full"
        viewBox="0 0 1280 720"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <rect width="1280" height="720" fill="#FAFAFA" />
        <polygon points="0,0 440,0 260,310 0,210" fill="#F1F1F3" />
        <polygon points="440,0 820,0 590,260 260,310" fill="#F7F7F8" />
        <polygon points="820,0 1280,0 1280,290 950,240 590,260" fill="#EDEDEF" />
        <polygon points="0,210 260,310 180,612 0,612" fill="#E8E8EB" />
        <polygon points="260,310 590,260 660,612 180,612" fill="#F4F4F6" />
        <polygon points="590,260 950,240 1050,612 660,612" fill="#FAFAFB" />
        <polygon points="950,240 1280,290 1280,612 1050,612" fill="#EFEFF2" />
        {/* Lower silver-gray floor band matching Slide 1 */}
        <defs>
          <linearGradient id="coverFloor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#D4D4D8" />
            <stop offset="100%" stopColor="#A1A1AA" />
          </linearGradient>
        </defs>
        <rect x="0" y="612" width="1280" height="108" fill="url(#coverFloor)" />
        <line x1="0" y1="612" x2="1280" y2="612" stroke="#D4D4D8" strokeWidth="1" />
      </svg>

      {/* 3D Rising Crimson Bar Chart & Arrow Graphic on Right */}
      <svg
        className="pointer-events-none absolute right-[44px] bottom-[56px] h-[590px] w-[620px]"
        viewBox="0 0 620 590"
        fill="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="barFront" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#DC2626" />
            <stop offset="100%" stopColor="#991B1B" />
          </linearGradient>
          <linearGradient id="barSide" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#7F1D1D" />
            <stop offset="100%" stopColor="#450A0A" />
          </linearGradient>
          <linearGradient id="barTop" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#F87171" />
            <stop offset="100%" stopColor="#DC2626" />
          </linearGradient>
          <filter id="barShadow" x="-10%" y="-10%" width="120%" height="130%">
            <feDropShadow dx="0" dy="10" stdDeviation="6" floodColor="#18181B" floodOpacity="0.24" />
          </filter>
        </defs>

        {/* Ground shadow */}
        <ellipse cx="325" cy="544" rx="275" ry="18" fill="#52525B" opacity="0.28" />

        {/* 7 stepped 3D red bars */}
        {[
          { x: 35, h: 105 },
          { x: 112, h: 138 },
          { x: 189, h: 168 },
          { x: 266, h: 208 },
          { x: 343, h: 262 },
          { x: 420, h: 332 },
          { x: 497, h: 416 },
        ].map((bar, idx) => {
          const baseY = 538;
          const topY = baseY - bar.h;
          const w = 52;
          const dx = 16;
          const dy = 11;
          return (
            <g key={idx} filter={idx === 0 || idx === 6 ? 'url(#barShadow)' : undefined}>
              {/* Front face */}
              <rect x={bar.x} y={topY} width={w} height={bar.h} rx="2" fill="url(#barFront)" />
              {/* Top face */}
              <polygon
                points={`${bar.x},${topY} ${bar.x + dx},${topY - dy} ${bar.x + w + dx},${topY - dy} ${bar.x + w},${topY}`}
                fill="url(#barTop)"
              />
              {/* Right side face */}
              <polygon
                points={`${bar.x + w},${topY} ${bar.x + w + dx},${topY - dy} ${bar.x + w + dx},${baseY - dy} ${bar.x + w},${baseY}`}
                fill="url(#barSide)"
              />
            </g>
          );
        })}

        {/* Sweeping 3D Crimson Arrow */}
        <g filter="url(#barShadow)">
          {/* Arrow shaft depth */}
          <path
            d="M 52 408 Q 290 308 492 104 L 478 96 Q 278 298 44 396 Z"
            fill="#7F1D1D"
          />
          {/* Arrow shaft main */}
          <path
            d="M 44 396 Q 280 296 485 94 L 500 109 Q 296 312 52 414 Z"
            fill="#DC2626"
          />
          {/* Arrow shaft highlight */}
          <path
            d="M 48 398 Q 280 298 486 96"
            stroke="#FCA5A5"
            strokeWidth="2.5"
            strokeLinecap="round"
            opacity="0.7"
          />
          {/* Arrow head 3D side */}
          <polygon points="528,36 538,44 522,138 510,126" fill="#7F1D1D" />
          {/* Arrow head main */}
          <polygon points="528,36 446,72 512,130" fill="#DC2626" />
          <polygon points="528,36 446,72 486,98" fill="#EF4444" />
        </g>
      </svg>
    </>
  );
}

export function SlideFrame({
  slideNumber,
  totalSlides,
  title,
  subtitle,
  isCover = false,
  showSourceFooter = false,
  children,
}: SlideFrameProps) {
  return (
    <div
      className="relative flex h-[720px] w-[1280px] flex-col overflow-hidden bg-white text-zinc-900 select-none"
      style={{ boxShadow: '0 24px 60px -15px rgba(0,0,0,0.38)' }}
    >
      {isCover ? (
        <>
          <CoverDecorations />
          <div className="relative z-10 flex-1 min-h-0 w-full">{children}</div>
        </>
      ) : (
        <>
          <TopLeftCrimsonWave />
          {/* Slide Header */}
          {title && (
            <header className="relative z-10 shrink-0 pr-[44px] pl-[170px] pt-[34px] pb-[10px]">
              <h2 className="font-display text-[32px] leading-[1.18] font-bold tracking-[-0.01em] text-[#9E0B0F] [text-wrap:balance]">
                {title}
              </h2>
              {subtitle && (
                <p className="mt-1 text-[14.5px] font-medium text-zinc-500">{subtitle}</p>
              )}
            </header>
          )}

          {/* Main Content Area expands to fill remaining height */}
          <div className="relative z-10 flex flex-1 min-h-0 w-full flex-col px-[44px] pt-[8px] pb-[6px]">
            {children}
          </div>

          {/* Subtle Compact Footer kept to left/right edges away from center dock */}
          <footer className="relative z-10 flex shrink-0 items-center justify-between px-[44px] pt-[4px] pb-[14px] text-[11.5px] text-zinc-400">
            <div className="flex items-center gap-2">
              <span>Adaptive Portfolio Risk Lab · CSS 342</span>
              {showSourceFooter && (
                <>
                  <span aria-hidden="true">·</span>
                  <span className="text-zinc-500">ข้อมูลย้อนหลัง · ตัดรอบ 2026-09-25</span>
                </>
              )}
            </div>
            <span className="font-mono-num font-medium text-zinc-500">
              หน้า {slideNumber} / {totalSlides}
            </span>
          </footer>
        </>
      )}
    </div>
  );
}

/**
 * Readable Mathematical Formula Components (Fraction, Square Root, Summation, Matrix)
 */
export function Fraction({
  num,
  den,
}: {
  num: React.ReactNode;
  den: React.ReactNode;
}) {
  return (
    <span className="inline-flex flex-col items-center align-middle mx-1 leading-none">
      <span className="border-b-[1.5px] border-zinc-800 px-1.5 pb-1 text-[0.88em]">
        {num}
      </span>
      <span className="px-1.5 pt-1 text-[0.88em]">{den}</span>
    </span>
  );
}

export function Radical({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-stretch align-middle mx-0.5">
      <svg
        className="w-[15px] shrink-0 text-zinc-800"
        viewBox="0 0 16 40"
        preserveAspectRatio="none"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M1 23 L4.5 23 L8 37 L14.5 2 L16 2"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="border-t-[1.8px] border-zinc-800 px-1.5 pt-1 pb-0.5 inline-flex items-center">
        {children}
      </span>
    </span>
  );
}

export function Summation({
  lower,
  upper,
}: {
  lower: React.ReactNode;
  upper: React.ReactNode;
}) {
  return (
    <span className="inline-flex flex-col items-center justify-center align-middle mx-1.5 leading-none">
      <span className="text-[11px] font-medium text-zinc-600 mb-0.5">{upper}</span>
      <span className="text-[24px] leading-none font-normal text-zinc-900">∑</span>
      <span className="text-[11px] font-medium text-zinc-600 mt-0.5">{lower}</span>
    </span>
  );
}

export function MathBox({
  formula,
  explanationTh,
}: {
  formula: React.ReactNode;
  explanationTh: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-zinc-50/90 px-5 py-3.5">
      <div className="font-mono-num flex flex-wrap items-center gap-1 text-[19px] font-medium text-zinc-900">
        {formula}
      </div>
      <p className="mt-2 border-t border-zinc-200/80 pt-2 text-[14px] leading-snug text-zinc-600">
        {explanationTh}
      </p>
    </div>
  );
}
