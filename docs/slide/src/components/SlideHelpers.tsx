import React, { useState } from 'react';

/* Slide 02 interactive Return vs Volatility toggle */
export function ReturnVsVolToggle() {
  const [focus, setFocus] = useState<'volatility' | 'return'>('volatility');

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="no-print flex items-center gap-2.5">
        <button
          type="button"
          onClick={() => setFocus('volatility')}
          className={`cursor-pointer rounded-lg px-4 py-2 text-[14.5px] font-bold transition-colors ${
            focus === 'volatility'
              ? 'bg-[#9E0B0F] text-white'
              : 'border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50'
          }`}
        >
          ความผันผวน (Volatility · สิ่งที่เราพยากรณ์)
        </button>
        <button
          type="button"
          onClick={() => setFocus('return')}
          className={`cursor-pointer rounded-lg px-4 py-2 text-[14.5px] font-bold transition-colors ${
            focus === 'return'
              ? 'bg-zinc-900 text-white'
              : 'border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50'
          }`}
        >
          ผลตอบแทน (Return · สิ่งที่ไม่ได้ทำนาย)
        </button>
      </div>

      {focus === 'volatility' ? (
        <div className="flex flex-1 flex-col justify-between rounded-xl border border-[#9E0B0F]/30 bg-red-50/40 p-6">
          <div>
            <div className="text-[20px] font-bold text-[#9E0B0F]">
              วัด &ldquo;ขนาดการแกว่งตัว&rdquo; ของราคา ไม่ทำนายทิศทางขึ้นหรือลง
            </div>
            <p className="mt-3 text-[16.5px] leading-relaxed text-zinc-800">
              ความผันผวนมักจับกลุ่มเป็นช่วงเวลา (Volatility Clustering) วันใดตลาดแกว่งแรง ช่วงถัดไปมักแกว่งต่อ จึงนำมาประเมินความเสี่ยงพอร์ตล่วงหน้า 5 วันได้แม่นยำกว่าการเดาทิศทางราคา
            </p>
          </div>
          <div className="mt-5 grid grid-cols-3 gap-3.5 text-[14px]">
            <div className="rounded-xl border border-red-200/80 bg-white px-4 py-3">
              <div className="font-bold text-zinc-900">1. พยากรณ์รายตัว</div>
              <div className="mt-1 text-zinc-600">Forward RV5 ราย ETF</div>
            </div>
            <div className="rounded-xl border border-red-200/80 bg-white px-4 py-3">
              <div className="font-bold text-zinc-900">2. รวมสหสัมพันธ์</div>
              <div className="mt-1 text-zinc-600">Correlation ย้อนหลัง 20 วัน</div>
            </div>
            <div className="rounded-xl border border-red-200/80 bg-white px-4 py-3">
              <div className="font-bold text-zinc-900">3. สำรวจพอร์ต</div>
              <div className="mt-1 text-zinc-600">ปรับน้ำหนัก w ได้ทันที</div>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-between rounded-xl border border-zinc-300 bg-zinc-50 p-6">
          <div>
            <div className="text-[20px] font-bold text-zinc-900">
              ผลตอบแทน (Return) บอก &ldquo;ทิศทางขึ้น/ลง&rdquo; ซึ่งผันผวนสูงจากข่าวรายวัน
            </div>
            <p className="mt-3 text-[16.5px] leading-relaxed text-zinc-800">
              โครงงานนี้ <strong>ไม่ได้พยากรณ์กำไรหรือขาดทุน</strong> ค่าที่โมเดลสร้างใช้ประเมินขนาดความแกว่งตัวของพอร์ตเพื่อบริหารความเสี่ยง ไม่ใช่สัญญาณซื้อขาย
            </p>
          </div>
          <div className="mt-5 rounded-xl border border-zinc-200 bg-white px-4.5 py-3.5 text-[14.5px] text-zinc-700">
            ตัวอย่าง: ค่าพยากรณ์ 20% ต่อปี หมายถึงขนาดการแกว่งที่อาจเกิดทั้งฝั่งบวกและลบ ไม่ได้แปลว่าราคาจะขึ้นหรือลง 20%
          </div>
        </div>
      )}
    </div>
  );
}

/* Slide 11 interactive step-by-step formula reveal */
export function PortfolioBridgeSteps() {
  const [step, setStep] = useState<number>(3);

  const steps = [
    {
      n: 1,
      title: 'ขั้นที่ 1: เวกเตอร์ส่วนเบี่ยงเบนมาตรฐาน (D)',
      formula: 'D = diag(σ̂_SPY, σ̂_IEF, σ̂_GLD)',
      desc: 'นำค่าพยากรณ์ความผันผวนรายปีของแต่ละ ETF ณ วันอ้างอิง t มาเรียงบนเส้นทแยงมุม',
    },
    {
      n: 2,
      title: 'ขั้นที่ 2: สร้างเมทริกซ์ความแปรปรวนร่วม (Σ)',
      formula: 'Σ = D · R₂₀ · D',
      desc: 'คูณเมทริกซ์ D กับสหสัมพันธ์ย้อนหลัง 20 วัน (R₂₀) เพื่อสะท้อนการเคลื่อนไหวร่วมกัน',
    },
    {
      n: 3,
      title: 'ขั้นที่ 3: ความผันผวนพอร์ต (σ_พอร์ต)',
      formula: 'σ_พอร์ต = √(wᵀ · Σ · w)',
      desc: 'คูณกับน้ำหนักที่ผู้ใช้เลือก (w) เพื่อประเมินความเสี่ยงรวมทันที โดยไม่ต้องฝึกโมเดลใหม่',
    },
  ];

  return (
    <div className="flex h-full flex-col justify-between gap-3.5">
      <div className="no-print flex items-center justify-between">
        <span className="text-[14px] font-bold text-zinc-700">ลำดับการคำนวณความเสี่ยงพอร์ต</span>
        <div className="flex gap-1.5">
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setStep(n)}
              className={`cursor-pointer rounded-md px-3.5 py-1.5 text-[12.5px] font-bold ${
                step === n
                  ? 'bg-[#9E0B0F] text-white'
                  : 'border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50'
              }`}
            >
              ถึงขั้นที่ {n}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-1 flex-col justify-between gap-3">
        {steps.map((s) => {
          const visible = s.n <= step;
          return (
            <div
              key={s.n}
              className={`flex flex-1 flex-col justify-center rounded-xl border px-5 py-4 transition-all ${
                visible
                  ? s.n === step
                    ? 'border-[#9E0B0F] bg-red-50/40'
                    : 'border-zinc-200 bg-white'
                  : 'border-dashed border-zinc-200 bg-zinc-50 opacity-45'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[15px] font-bold text-[#9E0B0F]">{s.title}</span>
                <span className="font-mono-num text-[15px] font-bold text-zinc-900">{s.formula}</span>
              </div>
              <p className="mt-1.5 text-[14.5px] text-zinc-700">{s.desc}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* Slide 14 static limitations layout (no interaction) */
export function LimitationsStaticGrid() {
  const items = [
    {
      tag: '1. รูปแบบการจำลอง',
      title: 'Historical Replay ≠ การเทรดจริง (Live PIT)',
      body: 'ประเมินจากข้อมูลย้อนหลังที่บันทึกไว้ ยังไม่ได้ตรวจยืนยันสภาพ Point-in-Time (PIT) แบบการรับราคาสดรายวัน',
    },
    {
      tag: '2. ขอบเขตข้อมูล',
      title: '3 ETF และชุด Test เพียง 1 ปีเดียว',
      body: 'ผลลัพธ์มาจาก SPY, IEF และ GLD ช่วง 1 ต.ค. 2025 – 25 ก.ย. 2026 จึงยังไม่อ้างข้ามไปยังตลาดหรือช่วงเวลาอื่น',
    },
    {
      tag: '3. สมมติฐานพอร์ต',
      title: 'Correlation ย้อนหลัง 20 วัน · ไม่มี P&L',
      body: 'สหสัมพันธ์ R₂₀ เป็นค่าประมาณย้อนหลัง ไม่ได้พยากรณ์สหสัมพันธ์ล่วงหน้า และไม่รวมกำไรขาดทุนหรือค่าธรรมเนียม',
    },
    {
      tag: '4. บันทึกความโปร่งใส',
      title: 'Working Tree Dirty & รอ Peer Review',
      body: 'Git ระหว่างรัน H1 มี Working tree dirty, High-vol ของ IEF มี n = 0 (ไม่เข้าเกณฑ์) และรอตรวจทานจากผู้ทรงคุณวุฒิ',
    },
  ];

  return (
    <div className="flex h-full flex-col justify-between gap-4">
      <div className="grid flex-1 grid-cols-2 gap-4">
        {items.map((item) => (
          <div
            key={item.tag}
            className="flex flex-col justify-center rounded-xl border border-zinc-200 bg-white p-5.5"
          >
            <div className="text-[13px] font-bold text-[#9E0B0F]">{item.tag}</div>
            <div className="font-display mt-1 text-[18px] font-bold text-zinc-900">
              {item.title}
            </div>
            <p className="mt-2 text-[15px] leading-relaxed text-zinc-700">{item.body}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 text-[14.5px]">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/55 px-5 py-3.5 text-emerald-950">
          <strong>สิ่งที่อ้างได้:</strong> ในชุดข้อมูลนี้ Pipeline ผ่านเกณฑ์ 100% และ B3 ลด Error จาก B2/B1 ได้อย่างมีนัยสำคัญ
        </div>
        <div className="rounded-xl border border-amber-200 bg-amber-50/60 px-5 py-3.5 text-amber-950">
          <strong>สิ่งที่ยังอ้างไม่ได้:</strong> ความเป็นเหตุและผล ผลตอบแทนการลงทุนจริง หรือผลลัพธ์นอกเหนือจาก 3 ETF นี้
        </div>
      </div>
    </div>
  );
}

