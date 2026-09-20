# FIDM 2023-2024 Replication Assignment — Stata 执行清单

**状态：** DRAFT（等待用核对 Morse et al. (2011) 原文后定稿）
**来源文件：** `Replication_Instruction_FIDM_2023_2024.docx` + `Stata_workshop_2023-2024.pptx`
**配套代码：** `code/replication_fidm.do`

---

## 0. 交付物（先记住终点）

| 文件 | 内容 |
|---|---|
| `execucomp_morse.dta` | 只含跑回归 (1)(2) 需要的变量 |
| `extension_exercise.dta` | 只含跑回归 (3) 需要的变量 |
| 一个 `.do` 文件 | 清洗 + 造变量 + 合并 + 回归，全部代码 |
| 2 页 PDF | 组员名单、变量定义与算法、提请 grader 注意的问题、三张结果表、结果解读、政策含义 |

全部放进一个 Dropbox 文件夹，只把**链接**交到 Canvas。截止：10 月 14 日 09:00。

---

## 1. 变量用途对照表（最关键的一张表）

Instruction 让你下载的每个变量都有唯一用途，没有多余的：

### `execucomp_executive`（Annual Compensation，executive-year 层）

| Execucomp 变量 | 在模型里的角色 |
|---|---|
| `TDC1` | 被解释变量 `LnTDC = log(tdc1)` |
| `CEOANN` | 样本筛选：`keep if ceoann == "CEO"` |
| `TITLE` | PowerIndex 成分：是否兼任 Chairman / President |
| `BECAMECEO` | `Tenure = year - year(becameceo)`、`Tenure_squared`；可能也是 PowerIndex 成分 |
| `SHROWN_EXCL_OPTS_PCT` | 控制变量 `Sharesowned`、`Sharesowned_squared`；可能也是 PowerIndex 成分 |
| `OPTION_AWARDS_BLK_VALUE` | 控制变量 `Optionsvalue` |

### `execucomp_perforamance`（Company Financial，firm-year 层；文件名拼写按 instruction 原样）

| Execucomp 变量 | 在模型里的角色 |
|---|---|
| `ASSETS` | 控制变量 `LnAsset = log(assets)` |
| `ROA` | `zROA`、`lag_zROA` |
| `PRCCF` + `AJEX` | 合起来算年度股票收益率 `Rstock` → `zRstock`、`lag_zRstock` |
| `BS_VOLATILITY` | 控制变量 `Volatility` |
| `SIC` | 行业代码：行业-年度标准化的分组变量，和/或样本剔除（金融/公用事业） |
| `GVKEY` + `YEAR` | merge key、panel id、firm FE / year FE |

**`AJEX` 的存在是决定性线索：** 它只有一个用途 —— `PRCCF` 是未经拆股调整的年末收盘价，`PRCCF/AJEX` 才是可比价格。所以

```
Rstock_t = (PRCCF_t / AJEX_t) / (PRCCF_{t-1} / AJEX_{t-1}) - 1
```

**注意：** 这是**价格收益率，不含股息**，因为 instruction 没让你下 `TRS1YR`。这一点必须写进 PDF 的变量定义。

---

## 2. 完整步骤（对应 `code/replication_fidm.do` 的各节）

### 第 0 步：环境准备
1. 建 `Stata workshop/{code, data, result}` 三个子文件夹（workshop Exercise 0）。
2. `ssc install winsor2, outreg2, unique, reghdfe, ftools`（reghdfe 依赖 ftools）。
3. `cd` 到项目根目录 —— 整个 do 文件里**只有这一行**是机器相关的，其余全用相对路径。
4. `log using "result/replication_log.smcl", replace`。

### 第 1 步：下载数据（WRDS）
- Compustat–Capital IQ → Execucomp → **Annual Compensation**，1992–2005，Ticker + "search the entire database"，选上表 6 个变量，输出 `.dta`，改名 `execucomp_executive`。
- Compustat–Capital IQ → Execucomp → **Company Financial and Director Compensation for 2005 and prior**，同样的日期与公司范围，选上表 6 个变量，输出 `.dta`，改名 `execucomp_perforamance`。
- 下载下来通常是 zip，解压后把 `.dta` 放进 `data/`。

### 第 2 步：清洗 executive 文件
1. `describe` / `codebook` —— **先看变量类型**（string 还是 numeric）。
2. `keep if ceoann == "CEO"`。
3. 统一 `gvkey` 类型（本 do 文件统一用 numeric）。**跨数据集类型不一致是 merge 失败的头号原因。**
4. `duplicates report gvkey year` → `duplicates list` 看一眼 → 再决定丢弃规则。重复来自年内 CEO 更替；本模板保留 TDC1 较高者，你要在 PDF 里写明你的规则。
5. `isid gvkey year` 断言唯一。
6. `drop if missing(tdc1) | tdc1<=0` → `gen LnTDC = log(tdc1)`。
7. `BECAMECEO` → `Tenure`、`Tenure_squared`（若是字符串先 `date()`；`Tenure<0` 置缺失）。
8. `SHROWN_EXCL_OPTS_PCT` → `Sharesowned`、`Sharesowned_squared`。
9. `OPTION_AWARDS_BLK_VALUE` → `Optionsvalue`（单位是**千美元**，缩放方式必须在 PDF 写明）。
10. `TITLE` → `lower()` 后用 `strpos()` 造 `d_chairman`、`d_president`（`strpos` 是 workshop Ex.12 教的）。**造完一定要 `tab title if d_chairman==1` 抽查**，别盲信字符串匹配。
11. `keep` 需要的列 → `save "temp/exec_clean.dta"`。

### 第 3 步：清洗 performance 文件
1. 同样 `describe`、统一 `gvkey` 类型、`duplicates drop gvkey year, force`、`isid`。
2. `LnAsset = log(assets)`（先剔除 `assets<=0`）。
3. `rename bs_volatility Volatility`。
4. `xtset gvkey year` → `gen prc_adj = prccf/ajex` → `gen Rstock = prc_adj/L.prc_adj - 1`（`L.` 是 workshop Ex.15）。
5. `SIC` → 补齐 4 位 → `sic2 = substr(sic_str,1,2)`（workshop Ex.12）。
6. `save "temp/perf_clean.dta"`。

### 第 4 步：合并
```stata
use "temp/exec_clean.dta", clear
merge 1:1 gvkey year using "temp/perf_clean.dta"
tab _merge          // 三个数字要写进 PDF
keep if _merge == 3
drop _merge
xtset gvkey year
```
两边都已 `isid gvkey year`，所以是 `1:1` 而不是 workshop Ex.19 的 `m:1`。

### 第 5 步：缩尾
`winsor2 roa Rstock LnAsset Volatility Sharesowned Optionsvalue Tenure, cuts(1 99) replace`
**缩尾之后要重新生成平方项**，否则 `Sharesowned_squared` 和 `Sharesowned` 对不上。

### 第 6 步：zROA / zRstock（⚠️ 全篇最关键的判断）
两个业绩指标必须放到**同一把尺子**上，否则 `Max`（"哪个指标今年更好看"）毫无意义。标准化的分组有三种合理选择：

| 方案 | 含义 | 代码 |
|---|---|---|
| A. 按年度 | 相对当年全体公司 | `bysort year: egen ...` |
| B. 按 sic2–年度 | 相对同业同年 | `bysort sic2 year: egen ...` |
| C. 按公司 | 相对公司自身历史 | `bysort gvkey: egen ...` |

do 文件里三种都写好了，默认启用 A，另外两种注释掉。**去读 Morse et al. (2011) Table II / Table III 的表注**，选定一种，并在 PDF 里写明。（如果论文用的是行业-年度，那 `SIC` 出现在下载清单上就解释得通了。）

然后：
```stata
xtset gvkey year
gen lag_zROA    = L.zROA
gen lag_zRstock = L.zRstock
```

### 第 7 步：Max
```stata
gen byte Max = (zRstock > zROA) if !missing(zRstock, zROA)
tab Max     // 大致 50/50；明显偏离说明第 6 步的标准化有问题
```
这就是"rigging"检验的核心：有权力的 CEO 是否更能按当年**看起来更好的**那个指标拿钱。

### 第 8 步：PowerIndex
可用的原料只有 `TITLE`、`BECAMECEO`、`SHROWN_EXCL_OPTS_PCT`，所以候选成分就是这四个 0/1：

- `d_chairman`（兼任董事长）
- `d_president`（兼任总裁）
- `d_tenure_high`（任期高于中位数）
- `d_own_high`（持股比例高于中位数）

```stata
egen byte PowerIndex = rowtotal(d_chairman d_president d_tenure_high d_own_high)
replace  PowerIndex = . if missing(d_chairman, d_president, d_tenure_high, d_own_high)
tab PowerIndex, missing
```
**成分清单和阈值必须对照论文 Data 部分核实后定稿**，并在 PDF 里逐条写出定义。
再造交互项：`gen MaxPowerIndex = Max * PowerIndex`。

### 第 9 步：样本筛选
1. `keep if inrange(year, 1992, 2005)`。
2. 考虑剔除金融业（SIC 6000–6999）与公用事业（SIC 4900–4949）—— 薪酬文献的惯例，**去论文里确认是否要做**。
3. 用 `rowmiss()` 做 listwise deletion，保证第 (1) (2) 列样本完全一致（模板表里两列 N 都是 8,263）。
4. `unique gvkey`、`count` 检查规模，目标量级约 8,000 观测。
5. `tabstat ..., stat(N mean sd min p25 median p75 max)` 出描述性统计（workshop Ex.7），PDF 里放得下就放。

### 第 10 步：回归
```stata
egen long firm_id = group(gvkey)      // absorb() 需要数值型
global CONTROLS LnAsset Volatility Sharesowned Sharesowned_squared ///
                Optionsvalue Tenure Tenure_squared

* 第 (1) 列：level effect
reghdfe LnTDC PowerIndex zROA zRstock lag_zROA lag_zRstock $CONTROLS, ///
        absorb(firm_id year) vce(cluster firm_id)
gen byte esample = e(sample)          // 锁住样本，保证第 (2) 列 N 相同

* 第 (2) 列：rigging effect
reghdfe LnTDC PowerIndex MaxPowerIndex zROA zRstock lag_zROA lag_zRstock ///
        $CONTROLS if esample, absorb(firm_id year) vce(cluster firm_id)
```
`reghdfe` 是 workshop Ex.18 教的双向固定效应命令；标准误按公司聚类（论文做法），表里写 Firm FE = YES、Year FE = YES。

### 第 11 步：出表
```stata
outreg2 using "result/table_main.rtf", replace word label nocons se bdec(3) sdec(3) ///
    addstat("R-squared", e(r2)) addtext("Firm FE","YES","Year FE","YES") ///
    ctitle("Table II column (1)") title("Table 1. ...")
```
第二列用 `append`。"Self-contained" 的意思是：表里要有变量名、系数、括号里的标准误、显著性星号、N、R²、FE 行、以及表注说明标准误类型和样本期。

### 第 12 步：保存 `execucomp_morse.dta`
`keep` 只留回归用得上的列，`order` 排好序，`compress`，`save`。

### 第 13 步：扩展题
1. https://osf.io/fd6jq/ 下载 `firmyear_score_2021Q4_Version_2022_Nov_22.csv`。
2. `import delimited ..., clear varnames(1) case(lower)`。
3. `keep gvkey year cc_expo_ew`，**把 `gvkey` 转成和 `execucomp_morse.dta` 完全相同的类型**。
4. `duplicates drop gvkey year, force` → `isid gvkey year` → 存临时文件。
5. `merge 1:1 gvkey year` 回 `execucomp_morse.dta`，`keep if _merge==3`。
6. `tab year` —— OSF 数据从 2002 年开始，Execucomp 样本到 2005 年，**交集只有 2002–2005**，这就是模板表里 N 只有 2,450 的原因，要在 PDF 里解释。
7. 把 `ClimateChange_Exposure` 加进 rigging 回归，`outreg2` 出第三张表。
8. `save "data/extension_exercise.dta", replace`。

---

## 3. 必须写进 PDF "issues for the grader" 的几件事

1. **方程 (2) 与模板表不一致。** Instruction 的方程 (2) 写了控制向量 `X'b`，但模板表第 (2) 列的 `LnAsset`、`Volatility` 等行是空的。说明你选了哪种做法（建议按方程加控制变量，表里用 `keep()` 隐藏并加一行 "Controls: YES"），并把这个不一致指出来。
2. **`Max` 主效应缺失。** 方程 (2) 里只有 `PowerIndex × Max`，没有 `Max` 单独项。标准做法是把组成项一起放进去。说明你的选择。
3. **模板表里的 `7` 后缀。** `Volatility7`、`Sharesowned7`、`Optionsvalue7`、`Tenure7` 在扩展表里又变成无后缀版本，且系数量级差了 100 倍以上（`Optionsvalue7 = 3.066` vs `Optionsvalue = 0.000`）。这是缩放/单位差异，不是不同变量。**把你自己用的单位明确写出来**。
4. **`Rstock` 不含股息**（没让下 `TRS1YR`）。
5. **CEO 年内更替造成的 gvkey-year 重复**，你的处理规则。
6. **zROA / zRstock 的标准化分组**，你选了哪个、依据是什么。
7. **`_merge` 三类的观测数**，以及最终样本量与论文的差距。

---

## 4. Workshop 技能 → 本作业的映射

| Workshop 练习 | 用在哪一步 |
|---|---|
| Ex.0 文件夹结构、Ex.2 `cd` | 第 0 步 |
| Ex.1 `use` / `save, replace` / `clear` | 全程 |
| Ex.3 `browse` / `order` / `unique` / `tab` | 第 2、3、9 步 |
| Ex.4 `rename` / `label variable` | 第 2、3 步 |
| Ex.5 `duplicates list` / `duplicates drop` | 第 2、3、13 步 |
| Ex.6 `xtset` | 第 3、4、6 步 |
| Ex.7 `sum` / `tabstat` / `hist` | 第 9 步 |
| Ex.9 `winsor2` | 第 5 步 |
| Ex.10 `drop if` / `keep if` | 第 2、9 步 |
| Ex.11 `gen` / `replace` / `log()` | 第 2、3、6、8 步 |
| Ex.12 `destring` / `tostring` / `strlen` / `substr` / `lower` / `strpos` / `year()` | 第 2、3 步 |
| Ex.13 `bysort ... : egen` | 第 6、8 步 |
| Ex.15 `L.` 滞后算子 | 第 3、6 步 |
| Ex.17 `reg` / `outreg2` | 第 10、11 步 |
| Ex.18 `reghdfe ..., absorb() vce()` | 第 10 步 |
| Ex.19 `merge` / `_merge` | 第 4、13 步 |

**Workshop 唯一没直接教、但本作业必须用的：** `winsor2` 之后重建平方项、`e(sample)` 锁样本、`isid` 断言、`rowtotal()` / `rowmiss()`。

---

## 5. 尚未确定、必须读原文核实的三件事

1. **PowerIndex 的确切成分与阈值** —— Morse et al. (2011) Data 部分。
2. **zROA / zRstock 的标准化基准组** —— Table II / Table III 表注。
3. **样本是否剔除金融业与公用事业** —— Data 部分。

这三条定了，剩下的全是机械执行。
