# ขั้นที่ 3: กำหนด Target Contract รายสินทรัพย์ และสัญญาการคำนวณความเสี่ยงพอร์ตโฟลิโอ (Target & Downstream Portfolio Risk Contract)

> **Target Contract** คือข้อตกลงและพันธสัญญาสำหรับการสร้างและตรวจสอบตัวแปรตาม (**Target / Label**) รายสินทรัพย์ (`asset_volatility_labels`) สำหรับฝึกและประเมินผลโมเดล Machine Learning รวมถึงกำหนดกติกาการนำค่าพยากรณ์ความผันผวนรายสินทรัพย์ไปคำนวณ**ความผันผวนของพอร์ตโฟลิโอในขั้นตอน Downstream** ตามน้ำหนักที่ผู้ใช้กำหนด
>
> สำหรับรายละเอียดคำอธิบายคอลัมน์ ชนิดข้อมูล (Type) หน่วยวัด (Unit) บทบาท (Role) และเงื่อนไข Nullable ของตาราง `asset_volatility_labels` และ `asset_rolling_correlations` ให้อ้างอิงจากแหล่งข้อมูลกลางที่ **[datadict.md](./datadict.md)**

---

## 1. ขอบเขตและนิยามของตัวแปรตามรายสินทรัพย์ (Asset-Level Target Specification)

| หัวข้อ | ข้อกำหนดและรายละเอียด |
| :--- | :--- |
| **ตารางผลลัพธ์ (Target Table)** | `asset_volatility_labels` |
| **ระดับหน่วยข้อมูล (Granularity)** | 1 แถว แทนค่าความผันผวนจริงในอนาคต 5 วันทำการถัดไป ($t+1$ ถึง $t+5$) ของ 1 สินทรัพย์ (`ticker`) ณ วันอ้างอิง `date` ($t$) |
| **คีย์หลัก (Primary Key)** | `(date, ticker)` โดยที่ `ticker` $\in \{\text{SPY}, \text{IEF}, \text{GLD}\}$ |
| **ชื่อคอลัมน์เป้าหมาย (Target Column)** | `target_realized_vol_5d` (`Role = Target (y)`) |
| **หน้าต่างเวลาเป้าหมาย (Forward Window)** | ผลตอบแทนลอการิทึมรายวันของสินทรัพย์ $i$ ในวันทำการถัดไป 5 วันทำการ: $\{r_{i,t+1}, r_{i,t+2}, r_{i,t+3}, r_{i,t+4}, r_{i,t+5}\}$ (**ไม่รวม**ผลตอบแทนของวัน $t$) |
| **ความสอดคล้องของสเกลกับ Feature** | ใช้หน่วย **Annualized Decimal** บนฐาน 252 วันทำการต่อปี เหมือนกับ `rv_5d`, `rv_20d`, `rv_60d` ใน [feature_contract.md](./feature_contract.md) ทุกประการ |

---

## 2. สูตรการคำนวณ Target รายสินทรัพย์ (`target_realized_vol_5d`)

กำหนดให้ $P_{i,s}^{\text{adj}}$ คือราคา `adjusted_close` ของสินทรัพย์ $i \in \{\text{SPY}, \text{IEF}, \text{GLD}\}$ ณ วันซื้อขาย $s$ และผลตอบแทนลอการิทึมรายวันคือ $r_{i,s} = \ln(P_{i,s}^{\text{adj}} / P_{i,s-1}^{\text{adj}})$:

1. **สูตร Annualized 5-Day Forward Realized Volatility ของสินทรัพย์ $i$ ณ วันอ้างอิง $t$**:
   $$y_{i,t} = \text{target\_realized\_vol\_5d}_{i,t} = \sqrt{\frac{252}{5} \sum_{k=1}^{5} r_{i,t+k}^{2}}$$
   โดยที่:
   - $r_{i,t+1} = \ln(P_{i,t+1}^{\text{adj}} / P_{i,t}^{\text{adj}})$ คือผลตอบแทนจากราคาปิดวัน $t$ ไปยังวันทำการถัดไป $t+1$
   - $r_{i,t+5} = \ln(P_{i,t+5}^{\text{adj}} / P_{i,t+4}^{\text{adj}})$ คือผลตอบแทนของวันทำการลำดับที่ 5 ถัดจากวัน $t$
2. **เงื่อนไขความสมบูรณ์ของ Label (`is_label_mature`)**:
   - ต้องมีข้อมูลผลตอบแทนในอนาคตของสินทรัพย์ $i$ ครบทั้ง 5 วันทำการ (`target_obs_count == 5`) จึงจะกำหนด `is_label_mature = True` และคำนวณค่า `target_realized_vol_5d`
   - สำหรับ 5 วันทำการล่าสุดของชุดข้อมูลที่ยังมีข้อมูลอนาคตไม่ครบ 5 วัน (`target_obs_count < 5`) ต้องกำหนด `is_label_mature = False` และให้ `target_realized_vol_5d = Null` (ห้ามคำนวณจากจำนวนวันที่ไม่ครบ 5 วันโดยเด็ดขาด)

---

## 3. โครงสร้างคอลัมน์ของตาราง `asset_volatility_labels`

| Column Name | Type | Role | กติกาการสร้างและการนำไปใช้ |
| :--- | :--- | :--- | :--- |
| `date` | `DATE` | Primary Key | วันซื้อขายอ้างอิง $t$ (ใช้ Join กับ `asset_volatility_features` ด้วย `(date, ticker)`) |
| `ticker` | `VARCHAR(16)` | Primary Key | รหัสหลักทรัพย์ (`'SPY'`, `'IEF'`, `'GLD'`) |
| `target_start_date` | `DATE` | Target Metadata | วันที่ของวันทำการ $t+1$ ของสินทรัพย์นั้น (ห้ามนำเข้า $X$) |
| `target_end_date` | `DATE` | Target Metadata | วันที่ของวันทำการ $t+5$ ของสินทรัพย์นั้น ใช้ตรวจสอบขอบเขต Purge/Embargo (ห้ามนำเข้า $X$) |
| `target_obs_count` | `INTEGER` | Target Metadata | จำนวนวันทำการที่มีผลตอบแทนจริงในช่วง $[t+1, t+5]$ มีค่าระหว่าง `0` ถึง `5` |
| `target_realized_vol_5d` | `FLOAT` | Target ($y$) | ค่าเป้าหมายสำหรับการฝึกและวัดผลโมเดลรายสินทรัพย์ (`Null` เมื่อ `is_label_mature == False`) |
| `is_label_mature` | `BOOLEAN` | Status | `True` เมื่อ `target_obs_count == 5` และ `target_realized_vol_5d` ไม่เป็น `Null` |
| `target_version` | `VARCHAR(16)` | Metadata | เวอร์ชันของสเปกการคำนวณ Target (เช่น `'2.0.0'`) |
| `run_id` | `VARCHAR(64)` | Metadata / Lineage | รหัสการสั่งรัน Target Pipeline ในรอบนั้น (Pipeline Execution Run ID เช่น `'lbl_run_20260925_001'`) |
| `source_batch_id` | `VARCHAR(64)` | Metadata / Lineage | รหัสชุดข้อมูลดิบต้นทาง (`market_prices_daily.source_batch_id` เช่น `'yf_batch_20260925_01'`) ที่ส่งต่อมาโดยไม่เปลี่ยนค่า |
| `label_as_of_utc` | `TIMESTAMPTZ` | Metadata / Audit | เวลา UTC ที่คำนวณแถวข้อมูลสำเร็จ (`YYYY-MM-DDTHH:MM:SSZ`) |

---

## 4. สัญญาการคำนวณความเสี่ยงพอร์ตโฟลิโอในขั้นตอน Downstream (Downstream Portfolio Risk Calculation Contract)

หลังจากโมเดลรายสินทรัพย์ทำนายค่าความผันผวนล่วงหน้า 5 วันของแต่ละสินทรัพย์ ณ วัน $t$ ได้เป็นเวกเตอร์ค่าพยากรณ์:
$$\hat{\boldsymbol{\sigma}}_{t} = \begin{bmatrix} \hat{\sigma}_{\text{SPY},t} \\ \hat{\sigma}_{\text{IEF},t} \\ \hat{\sigma}_{\text{GLD},t} \end{bmatrix}$$

ระบบจะคำนวณความเสี่ยงของพอร์ตโฟลิโอในขั้นตอน **Downstream** เมื่อผู้ใช้ระบุสัดส่วนน้ำหนักพอร์ตโฟลิโอตามข้อกำหนดดังนี้:

1. **การกำหนดน้ำหนักพอร์ตโฟลิโอของผู้ใช้ (User-Configurable Portfolio Weights)**:
   - เวกเตอร์น้ำหนักพอร์ตโฟลิโอ $\mathbf{w} = [w_{\text{SPY}}, w_{\text{IEF}}, w_{\text{GLD}}]^\top$ รับค่าจากผู้ใช้หรือ Application Layer ณ เวลาที่เรียกคำนวณ
   - เงื่อนไขความถูกต้องของน้ำหนัก (Long-only Fully Invested Default): $w_i \ge 0$ สำหรับทุกสินทรัพย์ และ $\sum_{i \in \{\text{SPY}, \text{IEF}, \text{GLD}\}} w_i = 1.0$
   - **ค่าเริ่มต้นสำหรับการสาธิต (Default Demonstration Weights)**: กำหนดค่าเริ่มต้นเป็นพอร์ต **`50/30/20`** ($w_{\text{SPY}} = 0.50, \; w_{\text{IEF}} = 0.30, \; w_{\text{GLD}} = 0.20$) ซึ่งผู้ใช้สามารถปรับเปลี่ยนเป็นสัดส่วนอื่นได้ตลอดเวลาโดยไม่ต้องสร้าง Feature หรือฝึกโมเดลรายสินทรัพย์ใหม่
2. **กติกาการใช้สหสัมพันธ์ย้อนหลังเป็นค่าประมาณสำหรับอนาคต (Historical Correlation Proxy & Point-in-Time Rule)**:
   - ณ วันอ้างอิง $t$ การคำนวณความเสี่ยงพอร์ตโฟลิโอสำหรับช่วง 5 วันข้างหน้า ($[t+1, t+5]$) **บังคับให้ใช้ค่าสหสัมพันธ์จากผลตอบแทนย้อนหลัง 20 วันทำการถึงวัน $t$ เท่านั้น ($\rho_{ij, t-19:t}$ จากตาราง `asset_rolling_correlations`)** เป็นตัวประมาณค่าความสัมพันธ์ในอนาคต ($\hat{\rho}_{ij, t+1:t+5} \approx \rho_{ij, t-19:t}$)
   - **ข้อจำกัดสำคัญที่ต้องระบุในรายงานและหน้า Dashboard**: ต้องระบุคำอธิบายอย่างชัดเจนในรายงานทางเทคนิคและแสดงข้อความกำกับบนหน้า Dashboard ว่า *"ค่าความผันผวนรายสินทรัพย์ ($\hat{\sigma}_{i,t}$) มาจากการพยากรณ์ล่วงหน้า 5 วันด้วยโมเดล Machine Learning ในขณะที่ค่าสหสัมพันธ์ระหว่างสินทรัพย์ ($\rho_{ij,t}$) ใช้ค่าสหสัมพันธ์ย้อนหลัง 20 วันทำการเป็น Historical Proxy ไม่ใช่ค่าสหสัมพันธ์ที่พยากรณ์จากโมเดล จึงอาจมีความคลาดเคลื่อนได้หากเกิดการเปลี่ยนระบอบความสัมพันธ์ (Correlation Regime Shift) อย่างฉับพลัน"*
3. **สูตรการรวมความผันผวนและการตรวจสอบเมทริกซ์ความแปรปรวนร่วม (Covariance Matrix Validation & Aggregation Formula)**:
   - กำหนดเมทริกซ์ส่วนเบี่ยงเบนมาตรฐานทแยงมุม $\mathbf{D}_t = \text{diag}(\hat{\sigma}_{\text{SPY},t}, \hat{\sigma}_{\text{IEF},t}, \hat{\sigma}_{\text{GLD},t})$ และเมทริกซ์สหสัมพันธ์ย้อนหลัง 20 วัน $\mathbf{R}_t = [\rho_{ij,t}]_{3\times 3}$ (โดย $\rho_{ii,t} = 1$) เพื่อสร้างเมทริกซ์ความแปรปรวนร่วมพยากรณ์:
     $$\hat{\boldsymbol{\Sigma}}_t = \mathbf{D}_t \mathbf{R}_t \mathbf{D}_t$$
   - **เกณฑ์การตรวจสอบเมทริกซ์ก่อนคำนวณพอร์ต (Mandatory Matrix Validation)**:
     1. **Synchronized Observations**: ค่า $\rho_{ij,t}$ ทั้ง 3 คู่ใน $\mathbf{R}_t$ ต้องคำนวณมาจากช่วงเวลา 20 วันทำการชุดเดียวกันที่มีข้อมูลผลตอบแทนครบทั้ง 3 สินทรัพย์พร้อมกัน
     2. **Bounds & Diagonal**: $\rho_{ii,t} = 1.0$ และ $\rho_{ij,t} \in [-1.0, 1.0]$ ทุกคู่
     3. **Symmetry**: $\mathbf{R}_t = \mathbf{R}_t^\top$ และ $\hat{\boldsymbol{\Sigma}}_t = \hat{\boldsymbol{\Sigma}}_t^\top$ (ภายในค่าคลาดเคลื่อนเชิงตัวเลข $10^{-12}$)
     4. **Positive Semidefiniteness (PSD)**: ค่าเจาะจงต่ำสุด $\lambda_{\min}(\mathbf{R}_t) \ge -10^{-10}$ และผลคูณกำลังสอง $\mathbf{w}^\top \hat{\boldsymbol{\Sigma}}_t \mathbf{w} \ge 0$
   - เมื่อผ่านการตรวจสอบครบทุกข้อ จึงคำนวณความผันผวนของพอร์ตโฟลิโอ:
     $$\hat{\sigma}_{p,t} = \sqrt{\mathbf{w}^\top \hat{\boldsymbol{\Sigma}}_t \mathbf{w}} = \sqrt{\sum_{i} w_i^2 \hat{\sigma}_{i,t}^2 + 2 \sum_{i < j} w_i w_j \hat{\sigma}_{i,t} \hat{\sigma}_{j,t} \rho_{ij,t}}$$
4. **นโยบายเมื่อข้อมูลหรือค่าพยากรณ์ไม่ครบองค์ประกอบ (Incomplete Portfolio Inputs & Dashboard Policy)**:
   - **ระดับโมเดลรายสินทรัพย์**: หาก `ticker` ใดตัวหนึ่งไม่ผ่าน Validation หรือถูกกักกัน (Quarantine) โมเดลของ `ticker` ที่เหลือซึ่งผ่านเกณฑ์ (`is_model_ready == True`) **ยังคงสร้างและแสดงค่าพยากรณ์รายสินทรัพย์ ($\hat{\sigma}_{i,t}$) ของตัวเองได้ตามปกติ**
   - **ระดับการคำนวณความเสี่ยงพอร์ตโฟลิโอ**: หากค่าพยากรณ์ $\hat{\sigma}_{i,t}$ ของสินทรัพย์ตัวใดตัวหนึ่งใน `{'SPY', 'IEF', 'GLD'}` ขาดหายไป **หรือ** เมทริกซ์สหสัมพันธ์ของวัน $t$ ไม่พร้อมใช้งาน (`is_corr_ready == False`) **ระบบต้องไม่คำนวณและไม่แสดงผลความเสี่ยงพอร์ตโฟลิโอของวันนั้น (`portfolio_vol = Null`, `status = 'INCOMPLETE_INPUTS'`)**
   - **การแสดงผลบน Dashboard**: หน้า Dashboard **ต้องแสดงสถานะแจ้งเตือนว่าข้อมูลไม่ครบถ้วนสำหรับการคำนวณพอร์ตโฟลิโอ** (พร้อมระบุรายการสินทรัพย์หรือเมทริกซ์ที่ขาดหาย) **ห้ามนำเฉพาะสินทรัพย์ที่เหลือมาคำนวณพอร์ตโฟลิโอหรือปรับน้ำหนักใหม่โดยเงียบๆ เด็ดขาด**
5. **ข้อตกลงกรณีคำนวณผลตอบแทนพอร์ตโฟลิโอจริงเพื่อเปรียบเทียบย้อนหลัง (Portfolio Return Convention for Backtesting)**:
   - เนื่องจากผลตอบแทนลอการิทึม (Log Return) ไม่สามารถบวกถ่วงน้ำหนักข้ามสินทรัพย์แบบเชิงเส้นได้โดยตรง ($\sum_i w_i r_{i,t} \ne r_{p,t}$) หากต้องการคำนวณผลตอบแทนรายวันของพอร์ตโฟลิโอที่ปรับสมดุลรายวัน (Rebalanced Portfolio Return) เพื่อใช้ในการวิเคราะห์ย้อนหลัง ต้องคำนวณจาก **Simple Return** ของแต่ละสินทรัพย์ก่อนเสมอ:
     $$R_{p,t} = \sum_{i \in \{\text{SPY}, \text{IEF}, \text{GLD}\}} w_i R_{i,t}, \qquad r_{p,t} = \ln(1 + R_{p,t})$$
   - ทั้งนี้ สูตรพอร์ตโฟลิโอข้างต้นใช้เฉพาะในโมดูลวิเคราะห์พอร์ตโฟลิโอ (Downstream Portfolio Analytics) เท่านั้น ห้ามนำไปใช้แทน Target รายสินทรัพย์ของโมเดลหลัก

