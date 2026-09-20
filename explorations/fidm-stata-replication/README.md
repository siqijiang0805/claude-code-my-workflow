# FIDM 2023-2024 Replication Assignment — Stata 执行清单

**状态：** CONFIRMED（变量定义已按老师提供的官方答案核实）
**来源：** `Replication_Instruction_FIDM_2023_2024.docx`、`Stata_workshop_2023-2024.pptx`、`Morse_et_al_replication_2023_-_solution.do`
**代码：**
- `code/official_solution.do` — 老师给的原版答案，不要改
- `code/replication_fidm.do` — Stata 版，变量定义与官方答案一致，另补上作业要求但答案漏掉的几句
- `code/replication_fidm_colab.ipynb` — **Google Colab notebook，直接上传就能跑**，与 `official_solution.do` 逐段一一对应
- `code/replication_colab.py` — 同一份代码的纯脚本版（读 `.dta`）
- `code/build_notebook.py` — 生成上面那个 ipynb 的脚本（改内容后重跑它）

### Python 版的三个语义陷阱

直译成 pandas 会出错的地方（`replication_colab.py` 里已处理）：

| solution.do | 直译的坑 | 正确做法 |
|---|---|---|
| `xtset` + `l.prccf` | `.shift(1)` 按**行位置**取上一行；某公司年份断档时会跨年错取 | 按 `(gvkey, year-1)` merge，见 `stata_lag()` |
| `replace max = zROA if zROA > zRstock` | Stata 把 missing 当 **+∞**；pandas 里 NaN 比较一律 False | `.max(axis=1, skipna=False)` |
| `merge 1:1` | Stata 默认保留 `_merge` 三类全部；pandas 默认 inner | `how="outer"` |
| `tostring sic` 后缺失变空串 | 空串在 Stata 里是**有效分组**；pandas `groupby` 默认丢弃 NaN 键 | 填成 `""` + `dropna=False` |
| `log(assets)`、`x/0` | Stata 给**缺失**；numpy 给 `-inf`/`inf`，会污染回归并让 `to_stata` 报 `ValueError` | `stata_log()` / `no_inf()` |

另外 `reghdfe ..., absorb() vce(robust)` 的对应物是 `pyfixest.feols("y ~ x | fe1 + fe2", vcov="hetero")`。

---

## 0. 交付物

| 文件 | 内容 |
|---|---|
| `execucomp_morse.dta` | **只含**跑回归 (1)(2) 需要的变量和行 |
| `extension_exercise.dta` | **只含**跑回归 (3) 需要的变量和行 |
| 一个 `.do` 文件 | 清洗 + 造变量 + 合并 + 回归，全部代码 |
| 2 页 PDF | 组员名单、变量定义与算法、提请 grader 注意的问题、结果表、结果解读、政策含义 |

全部放进一个 Dropbox 文件夹，只把链接交到 Canvas。截止：10 月 14 日 09:00。

---

## 1. 变量用途对照表

### `execucomp_executive`（Annual Compensation，executive-year 层）

| Execucomp 变量 | 角色 |
|---|---|
| `TDC1` | 被解释变量 `ln_tdc = log(TDC1)` |
| `CEOANN` | 样本筛选 `keep if ceoann == "CEO"` |
| `TITLE` | **PowerIndex 的唯一原料**（chairman / president 字符串匹配） |
| `BECAMECEO` | 控制变量 `tenure_ceo`、`tenure_ceo2`。**不进 PowerIndex** |
| `SHROWN_EXCL_OPTS_PCT` | 控制变量 `sharesowned`、`sharesowned2`。**不进 PowerIndex** |
| `OPTION_AWARDS_BLK_VALUE` | 控制变量 `optionsvalue` |

### `execucomp_perforamance`（Company Financial，firm-year 层；文件名拼写按 instruction 原样）

| Execucomp 变量 | 角色 |
|---|---|
| `ASSETS` | 控制变量 `LnAsset = log(assets)` |
| `ROA` | `zROA`、`lag_zROA` |
| `PRCCF` + `AJEX` | 合起来算年度股票收益率 `Rstock` → `zRstock`、`lag_zRstock` |
| `BS_VOLATILITY` | 控制变量 `Volatility` |
| `SIC` | **z-score 的分组变量**（sic2 × year）。不用来剔除行业 |
| `GVKEY` + `YEAR` | merge key、panel id、firm FE / year FE |

---

## 2. 三个曾经不确定、现已确定的定义

### 2.1 PowerIndex = 0 / 1 / 2 的序数变量

```stata
gen lower_title = lower(TITLE)
gen powerindex = 0
replace powerindex = 1 if strpos(lower_title,"chairman")>0 | ..."chairwoman"... | ..."chairperson"...
replace powerindex = 2 if (chairman|chairwoman|chairperson) & strpos(lower_title,"president")>0
```

| 值 | 含义 |
|---|---|
| 0 | 光杆 CEO |
| 1 | CEO 兼董事长 |
| 2 | CEO 兼董事长**且**兼总裁 |

两个容易看漏的点：

- **只兼总裁、不兼董事长的仍然是 0**（第二个 `replace` 要求 chairman 条件同时成立）。
- **tenure 和 ownership 不是 index 的成分**，只是控制变量。

### 2.2 Max 是连续变量，不是哑变量

```stata
gen max = 0
replace max = zROA    if zROA >  zRstock
replace max = zRstock if zROA <= zRstock
gen interaction = powerindex*max
```

`max = max(zROA, zRstock)` —— 今年哪个业绩指标更好看，就取**那个指标的标准化值**。instruction 里「a variable to capture the more *favorable* performance measure」说的就是 measure 的值。

`gen max = 0` 的初值永远活不下来：两个条件互斥且穷尽。缺失处理也是对的——Stata 把 missing 当 +∞，任一输入缺失时恰好触发其中一个 `replace`，赋成缺失。

### 2.3 z-score 的基准组 = `sic2 × year`

```stata
sort sic2 year
by sic2 year: egen mean_sic2_year_ROA = mean(ROA)
by sic2 year: egen std_sic2_year_ROA  = sd(ROA)
gen zROA = (ROA - mean_sic2_year_ROA) / std_sic2_year_ROA
```

即「相对同行业、同年度的同行」。这解释了 `SIC` 为什么在下载清单上。

**另外：金融业和公用事业不剔除。**

---

## 3. 执行顺序（顺序本身很重要）

```
performance 文件（全样本 firm-year）
  ├─ rename 大写→小写、destring gvkey、xtset
  ├─ LnAsset、Volatility、Rstock
  ├─ sic → sic2
  ├─ zROA / zRstock  ← 按 sic2×year，在全样本上算
  └─ lag_zROA / lag_zRstock
        ↓ save execucomp_perforamance1.dta
executive 文件
  ├─ powerindex（从 TITLE）
  ├─ rename、destring gvkey
  ├─ keep if ceoann=="CEO"
  ├─ tenure_ceo(+平方)、sharesowned2、ln_tdc
  └─ merge 1:1 gvkey year using perforamance1
        ↓
回归 (1) → outreg2 → 造 max、interaction → 回归 (2) → outreg2
        ↓ save execucomp_morse.dta
climate csv → keep 三列 → merge 1:1 → 回归 (3) → save extension_exercise.dta
```

**为什么 performance 必须先做：** z-score 的行业-年度均值/标准差要在**完整 firm-year 全样本**上算——此时还没筛 CEO、还没 merge。这样基准组是当年该行业的全部 Execucomp 公司，滞后项也能用上最终不进回归样本的年份。顺序反了结果就变了。

**为什么两列的 N 自动相同：** `interaction` 缺失 ⟺ `max` 缺失 ⟺ `zROA` 或 `zRstock` 缺失，而这两个在第一列已经是回归元，早被 listwise 剔掉了。不需要 `e(sample)` 之类的技巧。

---

## 4. 回归设定

```stata
global CONTROLS LnAsset Volatility sharesowned sharesowned2 optionsvalue ///
                tenure_ceo tenure_ceo2

* 第 (1) 列
reghdfe ln_tdc powerindex zROA zRstock lag_zROA lag_zRstock $CONTROLS, ///
        absorb(gvkey year) vce(robust)

* 第 (2) 列：只多一个 interaction，控制变量一个没少
reghdfe ln_tdc powerindex interaction zROA zRstock lag_zROA lag_zRstock $CONTROLS, ///
        absorb(gvkey year) vce(robust)
```

这也解决了 instruction 里的矛盾：**第 (2) 列是带控制变量的**，模板表里那些空单元格是旧版本残留，照方程 (2) 做即可。

出表：

```stata
outreg2 using "results/table1", excel replace ///
        ctitle(Table II column (1)) nocons dec(3) addtext(Firm FE, YES, Year FE, YES)
```

第二列用 `append`。注意是 `results` 文件夹（带 s），且 **outreg2 不会自动建文件夹**。

---

## 5. 官方答案里需要你补上的三处

| # | 问题 | 补什么 |
|---|---|---|
| 1 | 两处 merge 都只有 `drop _merge`，没有 `keep if _merge==3`；也没有 `keep <varlist>` | 两个 `.dta` 里会塞满进不了回归的行和用不到的列，违反「containing **only** those variables and data needed」。两句都要加 |
| 2 | `results` 文件夹不存在时 `outreg2` 直接报错 | `capture mkdir "results"` |
| 3 | 路径是 Windows 反斜杠 | Mac 上全改成 `/` |

---

## 6. PDF 里「issues for the grader」可以写的

1. **TITLE 缺失 → powerindex = 0**。`strpos("", "chairman")` 返回 0，于是「没有头衔信息」被编码成「没有权力」，是 measurement error。用 `count if missing(TITLE)` 量化一下。
2. **方程 (2) 没有 `max` 主效应**，只有交互项；而 `max` 是 `zROA`/`zRstock` 的非线性函数，两者都在模型里。交互项系数可能吸收了部分主效应。
3. **全程不缩尾**。Execucomp 的 ROA、Rstock 有极端值。
4. **`vce(robust)` 而非按公司聚类**。面板数据的惯例是聚类到公司。
5. **`Rstock` 不含股息**（instruction 没让下 `TRS1YR`，只有 `PRCCF`/`AJEX`），是价格收益率。
6. **`_merge` 三类的观测数**，以及最终样本量与论文的差距。
7. **扩展题只覆盖 2002–2005**：OSF 数据从 2002 开始，Execucomp 样本到 2005 年止，这就是模板表 N 只有 2,450 的原因。
8. **模板表的 `7` 后缀不用追**。官方答案里没有这套变量，用的是 Execucomp 原始单位（`sharesowned` 是百分数、`optionsvalue` 是千美元），出来的系数量级与**扩展表**那一列吻合。主表的 `7` 变量是更早一版、缩放不同的产物。

---

## 7. Workshop 技能 → 本作业的映射

| Workshop 练习 | 用在哪 |
|---|---|
| Ex.0 文件夹结构、Ex.2 `cd` | 第 0 节 |
| Ex.1 `use` / `save, replace` / `clear` | 全程 |
| Ex.3 `unique` / `tab` / `order` | 检查与出描述统计 |
| Ex.4 `rename` / `label variable` | §2.1、§3.2 |
| Ex.5 `duplicates list` / `duplicates drop` | §2.2、§6 |
| Ex.6 `xtset` | §2.2、§2.3 |
| Ex.7 `sum` / `tabstat` | 描述统计 |
| Ex.10 `keep if` / `drop if` | §3.3、merge 之后 |
| Ex.11 `gen` / `replace` / `log()` | 全程 |
| Ex.12 `destring` / `tostring` / `strlen` / `substr` / `lower` / `strpos` / `year()` | §2.3、§3.1、§3.4 |
| Ex.13 `by ... : egen` | §2.3 的 z-score |
| Ex.15 `l.` 滞后算子 | `Rstock`、`lag_zROA`、`lag_zRstock` |
| Ex.17 `outreg2` | §5 |
| Ex.18 `reghdfe ..., absorb() vce()` | §5 |
| Ex.19 `merge` / `_merge` | §4、§6 |

workshop 里没直接教、但答案用到的：`isid`（断言唯一）、`strpos` 的多条件组合、`replace sic = "0" + sic`（字符串拼接补前导零）。
