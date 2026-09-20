import json, pathlib

C = []
def md(s):   C.append(("markdown", s.strip("\n")))
def code(s): C.append(("code", s.strip("\n")))

# ----------------------------------------------------------------- intro
md(r"""
# FIDM 2023-2024 Replication Assignment — Colab 版

严格对应 `Morse_et_al_replication_2023_-_solution.do`，**一段一段一一对应，不多做任何一步**。
每个 `§编号` 就是 do 文件里同一个 `§编号`。

从上往下依次运行即可。

---

### 和 Stata 不一样、必须手工处理的四处

| solution.do | 直译成 pandas 的坑 | 本文件的做法 |
|---|---|---|
| `xtset` + `l.prccf` | `.shift(1)` 按**行位置**取上一行，公司年份断档时会跨年错取 | 按 `(gvkey, year-1)` merge，见 `stata_lag()` |
| `replace max = zROA if zROA > zRstock` | Stata 把 missing 当 **+∞**；pandas 里 NaN 比较一律 False | `.max(axis=1, skipna=False)` |
| `merge 1:1` | Stata 默认保留 `_merge` 三类全部；pandas 默认 inner | `how="outer"` |
| `tostring sic` 后缺失变空串 | 空串在 Stata 里是一个**有效分组**；pandas `groupby` 默认丢弃 NaN | 把缺失填成 `""` 再分组 |
| `log(assets)`、`x/0` | Stata 给**缺失**；numpy 给 `-inf` / `inf`，会一路污染回归并让 `to_stata` 报错 | `stata_log()` / `no_inf()` |

`reghdfe ..., absorb() vce(robust)` 的对应物是 `pyfixest.feols("y ~ x | fe1 + fe2", vcov="hetero")`。
""")

# ----------------------------------------------------------------- 0a
md("## §0-a　环境准备\n\ndo 文件里没有这一段（Stata 本地装好就能跑），但 Colab 每次开机都是空的。\n`pyfixest` 是 Stata `reghdfe` 的 Python 对应物，同样支持 `absorb()` 多维固定效应和 `vce(robust)`。")
code(r'''
!pip install -q pyfixest

import os
import numpy as np
import pandas as pd
import pyfixest as pf

pd.set_option('display.max_rows', 100)
pd.set_option('display.width', 200)

print("pandas", pd.__version__, "| pyfixest", pf.__version__)
''')

# ----------------------------------------------------------------- 0b
md(r"""## §0-b　挂载 Drive、设置路径

对应 do 文件的 `cd "C:\...\Replication_Assignment 2023"`。

输出会写到 `DATA` 的**上一级**目录下的 `results/` 里（和 do 文件的 `results\table1` 一致）。
""")
code(r'''
from google.colab import drive
drive.mount('/content/drive')

DATA      = "/content/drive/MyDrive/TA for laurence/data"
EXEC_FILE = "execucomp_executive.csv"
PERF_FILE = "execucomp_perforamance.csv"
CC_FILE   = "climatechage_exposure.csv"   # OSF 那个 firmyear_score_...csv 改名而来

# 总资产用哪一列。官方答案用 Execucomp 的 ASSETS；如果你的下载里这一列覆盖率很低
# （§2.1 会打印各列非缺失数），重下时多勾一个总资产字段，然后把列名填在这里。
ASSET_COL = "assets"

RESULTS = os.path.join(os.path.dirname(DATA), "results")
os.makedirs(RESULTS, exist_ok=True)       # outreg2 不会自动建文件夹，Python 也不会

p = lambda f: os.path.join(DATA, f)       # 拼数据路径的小助手
r = lambda f: os.path.join(RESULTS, f)    # 拼输出路径的小助手

print("data   :", DATA)
print("results:", RESULTS)
print(sorted(os.listdir(DATA)))
''')

# ----------------------------------------------------------------- 0c
md(r"""## §0-c　四个工具函数

这一段 do 文件里没有，但**不是多做的事**，而是补上 Stata 内建、Python 没有的功能。
不写这四个函数，下面的翻译就是错的或者会报错。

1. **`norm_cols()`** — 大小写不敏感地改名。WRDS 的 CSV 列名有时全大写有时全小写，写死一种会 KeyError。
2. **`stata_lag()`** — 复刻 Stata 的 `l.` 滞后算子。`l.x` 是"同一个 gvkey 在 `year-1` 那一年的 x"，某公司缺 1995 年时 1996 年的 `l.x` 就是缺失；`.shift(1)` 是"上一行"，会跨年错取。
3. **`stata_log()`** — 复刻 Stata 的 `log()`：`x <= 0` 返回**缺失**。
   numpy 不一样：`np.log(0) = -inf`、`np.log(负数) = nan`。
   `-inf` 会一路带进回归污染系数，`to_stata` 也会直接 `ValueError`。
4. **`no_inf()`** — 复刻 Stata 的除法：分母为 0 时结果是**缺失**，不是 `±inf`。
5. **`outreg2_like()`** — 复刻 `outreg2` 的输出：系数带星号、标准误在括号里、底部 N / R² / FE 行、导出 Excel。
6. **`to_dta()`** — `to_stata()` 的包装，处理日期列、可空类型、残留的 `±inf` 和不合法的变量名。
""")
code(r'''
def norm_cols(df, mapping):
    """大小写不敏感地改名；源文件里没有的键直接跳过。"""
    lut = {c.lower(): c for c in df.columns}
    ren = {lut[k.lower()]: v for k, v in mapping.items() if k.lower() in lut}
    return df.rename(columns=ren)


def need(df, cols, who):
    """缺列就立刻报错，别等到十几段之后才炸。"""
    miss = [c for c in cols if c not in df.columns]
    assert not miss, f"{who} 缺少这些列：{miss}\n实际列名：{df.columns.tolist()}"


def stata_log(x):
    """复刻 Stata 的 log()：x <= 0 返回缺失。
    numpy 不一样：np.log(0) = -inf，np.log(负数) = nan 并抛 RuntimeWarning。
    -inf 会一路带进回归污染系数，to_stata 也会直接报 ValueError。"""
    x = pd.to_numeric(x, errors="coerce")
    return np.log(x.where(x > 0))


def no_inf(s):
    """复刻 Stata 的除法：分母为 0 时结果是缺失，而不是 ±inf。"""
    return pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan)


def stata_lag(df, cols, by="gvkey", t="year", n=1):
    """复刻 Stata 的 l. 算子：按 (by, t-n) 取值，该年份不存在就是缺失。"""
    lag = df[[by, t] + cols].copy()
    lag[t] = lag[t] + n                                    # 整体往后挪 n 年
    lag = lag.rename(columns={c: f"l{n}_{c}" for c in cols})
    return df.merge(lag, on=[by, t], how="left")


def _attr(m, *names):
    for n in names:
        v = getattr(m, n, None)
        if v is not None:
            return v
    return np.nan


def outreg2_like(models, ctitles, path):
    """复刻 outreg2 ..., excel dec(3) addtext(Firm FE, YES, Year FE, YES)

    行顺序：把各模型的变量序列归并，让只出现在某一列的变量（比如
    interaction）落在它在该模型里的位置，而不是被甩到表格最末尾。"""
    order = []
    for m in sorted(models, key=lambda m: -len(m.tidy().index)):
        idx = list(m.tidy().index)
        for j, v in enumerate(idx):
            if v in order:
                continue
            prev = [u for u in idx[:j] if u in order]
            order.insert(order.index(prev[-1]) + 1 if prev else 0, v)

    cols = {}
    for m, ct in zip(models, ctitles):
        t = m.tidy()
        col = {}
        for v in t.index:
            b  = t.loc[v, "Estimate"]
            se = t.loc[v, "Std. Error"]
            pv = t.loc[v, "Pr(>|t|)"]
            star = "***" if pv < 0.01 else "**" if pv < 0.05 else "*" if pv < 0.10 else ""
            col[v]         = f"{b:.3f}{star}"              # 系数 + 显著性星号
            col[v + "_se"] = f"({se:.3f})"                 # 括号里的稳健标准误
        n  = _attr(m, "_N")
        r2 = _attr(m, "_r2", "_r2_within")
        col["Observations"] = f"{int(n):,}"    if np.isfinite(n)  else "n/a"
        col["R-squared"]    = f"{float(r2):.3f}" if np.isfinite(r2) else "n/a"
        col["Firm FE"]      = "YES"
        col["Year FE"]      = "YES"
        cols[ct] = col
    rows = [x for v in order for x in (v, v + "_se")]
    rows += ["Observations", "R-squared", "Firm FE", "Year FE"]
    out = pd.DataFrame(cols).reindex(rows).fillna("")
    out.to_excel(path)
    print("saved:", path)
    return out


def to_dta(df, path):
    """to_stata 的包装：处理日期列、可空类型、残留 ±inf、不合法的变量名。"""
    import re as _re
    out = df.copy()

    convert_dates = {}
    for c in out.columns:
        s = out[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            convert_dates[c] = "td"
        elif isinstance(s.dtype, pd.StringDtype) or s.dtype == object:
            out[c] = s.astype(object).where(s.notna(), "")
        elif str(s.dtype) in ("Int64", "Int32", "Int16", "Int8", "Float64", "boolean"):
            out[c] = s.astype("float64")

    # 最后一道保险：Stata 不接受 ±inf（这些运算在 Stata 里本来就该是缺失）
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            m = np.isinf(out[c].to_numpy())
            if m.any():
                print(f"  ⚠ {c}: {m.sum()} 个 ±inf 已转成缺失（去上游查一下为什么）")
                out[c] = out[c].replace([np.inf, -np.inf], np.nan)

    # Stata 变量名规则：≤32 字符、只能字母数字下划线、不能数字开头
    ren, seen = {}, set()
    for c in out.columns:
        n = _re.sub(r"\W", "_", str(c))[:32]
        if not n or n[0].isdigit():
            n = ("v" + n)[:32]
        base, k = n, 1
        while n in seen:
            k += 1
            n = f"{base[:29]}_{k}"
        seen.add(n)
        if n != c:
            ren[c] = n
    if ren:
        print("  变量名已调整:", ren)
    out = out.rename(columns=ren)
    convert_dates = {ren.get(k, k): v for k, v in convert_dates.items()}

    out.to_stata(path, write_index=False, version=117, convert_dates=convert_dates)
    print("saved:", path, out.shape)
''')

# ----------------------------------------------------------------- 1
md(r"""## §1　读入公司财务数据

对应 `use "data\execucomp_perforamance.dta", clear`（你的是 CSV，改用 `read_csv`）。

**注意整份 do 文件的顺序：先处理 performance 文件，后处理 executive 文件。**
这不是随意的 —— §2.3-c 的行业-年度标准化必须在"完整 firm-year 全样本"上算，
此时还没筛 CEO、还没 merge。顺序反了结果就变了。
""")
code(r'''
perf = pd.read_csv(p(PERF_FILE))

print(perf.shape)
print(perf.columns.tolist())
perf.head()
''')

# ----------------------------------------------------------------- 2.1
md(r"""## §2.1　变量改名

对应 `rename GVKEY gvkey` / `rename ASSETS assets` / ...

统一成小写。注意 do 文件里 **`ROA` 没有被 rename**，全文一直用大写 `ROA` —— 这里照做。
用 `norm_cols()` 是为了不管你的 CSV 列名是大写还是小写都能对上。
""")
code(r'''
perf = norm_cols(perf, {
    "GVKEY":         "gvkey",
    "ASSETS":        "assets",
    "PRCCF":         "prccf",
    "YEAR":          "year",
    "BS_VOLATILITY": "bs_volatility",
    "SIC":           "sic",
    "AJEX":          "ajex",
    "ROA":           "ROA",      # do 文件里保持大写
    "AT":            "at",       # 重下时若多勾了 Compustat 的 Total Assets，会落到这里
})

need(perf, ["gvkey", "year", ASSET_COL, "prccf", "ajex",
            "bs_volatility", "sic", "ROA"], "performance 文件")

print("各列非缺失数（对比 ROA 和 ASSET_COL —— 能算 ROA 就一定有总资产）：")
print(perf.notna().sum().sort_values(ascending=False).to_string())
''')

# ----------------------------------------------------------------- 2.2
md(r"""## §2.2　设成面板数据

对应：
```stata
duplicates list gvkey year
destring gvkey, replace
xtset gvkey year
```

- **`destring`**：WRDS 的 gvkey 是带前导零的字符串 `"001004"`，转成数字 `1004`。
  这一步必须做，否则 §4 的 merge 两边 key 类型对不上，**一条都匹配不上而且不报错**。
- **`xtset`**：Stata 里如果 `(gvkey, year)` 不唯一会直接报错终止。Python 没有这个机制，
  所以用 `assert` 手工复刻这个断言 —— do 文件能跑通，就说明它本来是唯一的。
""")
code(r'''
perf["gvkey"] = pd.to_numeric(perf["gvkey"], errors="coerce").astype("int64")
perf["year"]  = pd.to_numeric(perf["year"],  errors="coerce").astype("int64")

dup = perf.duplicated(subset=["gvkey", "year"]).sum()
print("duplicates on gvkey-year:", dup)
assert dup == 0, "gvkey-year 不唯一，Stata 的 xtset 在这里会报错"

perf = perf.sort_values(["gvkey", "year"]).reset_index(drop=True)
print(perf.shape)
''')

# ----------------------------------------------------------------- 2.3a
md(r"""## §2.3-a　公司层面控制变量

对应：
```stata
gen LnAsset = log(assets)
rename bs_volatility Volatility
gen Rstock = (prccf/ajex)/(l.prccf/l.ajex) - 1
```

`Rstock` 是年度股票收益率。`PRCCF` 是**未经拆股调整**的年末收盘价，拆股当年会跳水；
`AJEX` 是累计调整因子，`PRCCF/AJEX` 才是跨年可比的价格。

这里必须用 `stata_lag()`，**不能用 `.shift(1)`**。

（这是价格收益率，**不含股息** —— 因为作业没让下 `TRS1YR`。这点要写进 PDF 的变量定义。）
""")
code(r'''
perf[ASSET_COL] = pd.to_numeric(perf[ASSET_COL], errors="coerce")
print(f"{ASSET_COL} 非缺失:", perf[ASSET_COL].notna().sum(),
      f"| {ASSET_COL} <= 0:", (perf[ASSET_COL] <= 0).sum(), "  <- 这些行 LnAsset 会是缺失")

perf["LnAsset"] = stata_log(perf[ASSET_COL])       # Stata 的 log(0) 是缺失，不是 -inf
perf = perf.rename(columns={"bs_volatility": "Volatility"})

for c in ["prccf", "ajex"]:
    perf[c] = pd.to_numeric(perf[c], errors="coerce")

perf = stata_lag(perf, ["prccf", "ajex"])          # 生成 l1_prccf, l1_ajex
perf["Rstock"] = no_inf(                           # Stata 的 x/0 是缺失，不是 inf
    (perf["prccf"] / perf["ajex"]) / (perf["l1_prccf"] / perf["l1_ajex"]) - 1
)

print(perf[["gvkey", "year", "prccf", "ajex", "l1_prccf", "l1_ajex", "Rstock"]].head(8))
print("\nLnAsset 非缺失数:", perf["LnAsset"].notna().sum(),
      "| Rstock 非缺失数:", perf["Rstock"].notna().sum())
assert not np.isinf(perf[["LnAsset", "Rstock"]].to_numpy(dtype="float64")).any()
''')

# ----------------------------------------------------------------- 2.3b
md(r"""## §2.3-b　两位数行业代码

对应：
```stata
tostring sic, replace
replace sic = "0" + sic if strlen(sic) == 3
gen sic2 = substr(sic,1,2)
```

SIC 是 4 位数字，但 `700` 这种存成数值后只有 3 位，前面要补一个 `"0"` 变成 `"0700"`，
否则取前两位会拿到 `"70"` 而不是 `"07"`。

**缺失值要填成空串 `""`**：Stata 的 `tostring` 把数值缺失变成空串，而空串在
`by sic2 year:` 里是一个**有效分组**。pandas 的 `groupby` 默认会把 NaN 整行丢掉，
那些公司就拿不到 z-score 了 —— 和 Stata 行为不一致。
""")
code(r'''
sic_num = pd.to_numeric(perf["sic"], errors="coerce")
sic_str = sic_num.astype("Int64").astype("string").fillna("")     # tostring：缺失 -> ""
sic_str = sic_str.where(sic_str.str.len() != 3, "0" + sic_str)    # 3 位补前导零

perf["sic"]  = sic_str
perf["sic2"] = sic_str.str[:2]                                    # substr(sic,1,2)

print(perf["sic2"].value_counts(dropna=False).head(10))
print("\nsic2 为空串的行数:", (perf["sic2"] == "").sum())
''')

# ----------------------------------------------------------------- 2.3c
md(r"""## §2.3-c　标准化的业绩指标 zROA / zRstock

对应：
```stata
sort sic2 year
by sic2 year: egen mean_sic2_year_ROA = mean(ROA)
by sic2 year: egen std_sic2_year_ROA  = sd(ROA)
gen zROA = (ROA - mean_sic2_year_ROA) / std_sic2_year_ROA
```

**整个作业最关键的一步**：把会计业绩(`ROA`)和市场业绩(`Rstock`)放到同一把尺子上，
基准组是「同一个两位数行业、同一年」的全部 Execucomp 公司。
这也解释了 `SIC` 为什么会出现在下载清单上。

两个语义细节都是对上的：
- pandas 的 `transform("std")` 默认 `ddof=1`（样本标准差），和 Stata 的 `egen sd()` 一致
- 组内只有一个非缺失值时，两者都给缺失
- `egen` 和 `transform` 都自动跳过缺失值

`dropna=False` 是为了让 §2.3-b 里那些 `sic2 == ""` 的行也参与分组（同 Stata）。
""")
code(r'''
perf["ROA"] = pd.to_numeric(perf["ROA"], errors="coerce")

g = perf.groupby(["sic2", "year"], dropna=False)

perf["mean_sic2_year_ROA"]    = g["ROA"].transform("mean")
perf["std_sic2_year_ROA"]     = g["ROA"].transform("std")
perf["mean_sic2_year_Rstock"] = g["Rstock"].transform("mean")
perf["std_sic2_year_Rstock"]  = g["Rstock"].transform("std")

# no_inf：某个 sic2-year 组内标准差为 0 时，Stata 给缺失、numpy 给 inf
perf["zROA"]    = no_inf((perf["ROA"]    - perf["mean_sic2_year_ROA"])    / perf["std_sic2_year_ROA"])
perf["zRstock"] = no_inf((perf["Rstock"] - perf["mean_sic2_year_Rstock"]) / perf["std_sic2_year_Rstock"])

print(perf[["zROA", "zRstock"]].describe())
''')

# ----------------------------------------------------------------- 2.3d
md(r"""## §2.3-d　滞后一期的业绩指标

对应：
```stata
xtset gvkey year
gen lag_zROA    = l.zROA
gen lag_zRstock = l.zRstock
```

同样用 `stata_lag()`，按 `(gvkey, year-1)` 取值。

注意这一步是**在 merge 之前、在全样本上**做的，所以滞后项可以取到那些最终
进不了回归样本的年份 —— 这和 do 文件的行为一致。
""")
code(r'''
perf = stata_lag(perf, ["zROA", "zRstock"])
perf = perf.rename(columns={"l1_zROA": "lag_zROA", "l1_zRstock": "lag_zRstock"})

print(perf[["gvkey", "year", "zROA", "lag_zROA", "zRstock", "lag_zRstock"]].head(8))
''')

# ----------------------------------------------------------------- 2.4
md(r"""## §2.4　存中间文件

对应 `save "data\execucomp_perforamance1.dta", replace` + `clear all`。

Stata 一次只能在内存里放一个数据集，所以必须先存盘再去读高管文件；
Python 不存在这个限制，但 do 文件做了这一步，就照做。

> 嫌写 Drive 慢的话可以把这一格注释掉 —— 后面用的是内存里的 `perf`，不读这个文件。
""")
code(r'''
to_dta(perf, p("execucomp_perforamance1.dta"))
''')

# ----------------------------------------------------------------- 3
md(r"""## §3　读入高管数据

对应 `use "data\execucomp_executive.dta", clear`。
""")
code(r'''
exe = pd.read_csv(p(EXEC_FILE))

print(exe.shape)
print(exe.columns.tolist())
exe.head()
''')

# ----------------------------------------------------------------- 3.1
md(r"""## §3.1　PowerIndex —— CEO 权力指数

对应：
```stata
gen lower_title = lower(TITLE)
gen powerindex = 0
replace powerindex = 1 if strpos(lower_title,"chairman")>0 | ..."chairwoman"... | ..."chairperson"...
replace powerindex = 2 if (chairman|chairwoman|chairperson) & strpos(lower_title,"president")>0
```

这是一个 **0/1/2 的序数变量**，只看头衔兼任：

| 值 | 含义 |
|---|---|
| 0 | 光杆 CEO |
| 1 | CEO 兼董事长 |
| 2 | CEO 兼董事长**且**兼总裁 |

两个容易看漏的点：
- **只兼总裁、不兼董事长的仍然是 0**（第二个 `replace` 要求 chairman 条件同时成立）
- **tenure 和 sharesowned 不是指数的成分**，它们只是控制变量

`.fillna("")` 是在复刻 Stata：`TITLE` 缺失时 `lower()` 得到空串，`strpos` 返回 0，
于是 `powerindex = 0`。也就是说**"没有头衔信息"被编码成"没有权力"** —— 这是个
measurement issue，值得写进 PDF 的 issues 一节。
""")
code(r'''
exe = norm_cols(exe, {"TITLE": "TITLE"})
need(exe, ["TITLE"], "executive 文件")

lower_title = exe["TITLE"].fillna("").astype(str).str.lower()

chair = (lower_title.str.contains("chairman",    regex=False) |
         lower_title.str.contains("chairwoman",  regex=False) |
         lower_title.str.contains("chairperson", regex=False))
pres  =  lower_title.str.contains("president",   regex=False)

exe["powerindex"] = 0
exe.loc[chair,        "powerindex"] = 1
exe.loc[chair & pres, "powerindex"] = 2

print(exe["powerindex"].value_counts().sort_index())
print("\nTITLE 缺失行数（会被记成 powerindex=0）:", exe["TITLE"].isna().sum())
''')

# ----------------------------------------------------------------- 3.2
md(r"""## §3.2　变量改名 + destring

对应 `rename CEOANN ceoann` / `rename YEAR year` / ... / `destring gvkey, replace`。

`TDC1` 保持大写（do 文件里也没改）。
`gvkey` 的类型必须和 §2.2 里的**一模一样**，否则 §4 的 merge 匹配不上。
""")
code(r'''
exe = norm_cols(exe, {
    "CEOANN":                  "ceoann",
    "YEAR":                    "year",
    "SHROWN_EXCL_OPTS_PCT":    "sharesowned",
    "BECAMECEO":               "becameceo",
    "OPTION_AWARDS_BLK_VALUE": "optionsvalue",
    "GVKEY":                   "gvkey",
    "TDC1":                    "TDC1",      # do 文件里保持大写
})

need(exe, ["gvkey", "year", "ceoann", "sharesowned",
           "becameceo", "optionsvalue", "TDC1"], "executive 文件")

exe["gvkey"] = pd.to_numeric(exe["gvkey"], errors="coerce").astype("int64")
exe["year"]  = pd.to_numeric(exe["year"],  errors="coerce").astype("int64")

print(exe.columns.tolist())
''')

# ----------------------------------------------------------------- 3.3
md(r"""## §3.3　只保留 CEO

对应：
```stata
gen CEO = 0
replace CEO = 1 if ceoann == "CEO"
keep if CEO == 1
```

`CEOANN` 标记的是"该财年年末在任的 CEO"。
筛完之后每个 `gvkey-year` 应该只剩一行 —— §4 的 `validate="1:1"` 会替你检查。

> 如果筛完是 0 行，先看一眼 `exe["ceoann"].unique()`，可能有前后空格，加 `.str.strip()`。
""")
code(r'''
print("ceoann 取值:", exe["ceoann"].dropna().unique()[:10])

exe = exe[exe["ceoann"] == "CEO"].copy()

print("筛完 CEO 后:", exe.shape)
assert len(exe) > 0, "一行都没剩，检查 ceoann 的取值和空格"
''')

# ----------------------------------------------------------------- 3.4
md(r"""## §3.4　CEO 任期

对应：
```stata
gen tenure_ceo = year - year(becameceo)
replace tenure_ceo = . if year - year(becameceo) < 0
gen tenure_ceo2 = tenure_ceo^2
```

`becameceo` 在 CSV 里是字符串，要先 `to_datetime` 再取 `.dt.year`。
`errors="coerce"` 让解析不了的变成 `NaT`（等价于 Stata 的缺失日期）。
负数是数据错误（上任日期晚于观测年份），置成缺失。
""")
code(r'''
exe["becameceo"] = pd.to_datetime(exe["becameceo"], errors="coerce")
print("becameceo 解析失败的行数:", exe["becameceo"].isna().sum())

exe["tenure_ceo"] = exe["year"] - exe["becameceo"].dt.year
exe.loc[exe["tenure_ceo"] < 0, "tenure_ceo"] = np.nan
exe["tenure_ceo2"] = exe["tenure_ceo"] ** 2

print(exe["tenure_ceo"].describe())
''')

# ----------------------------------------------------------------- 3.5
md(r"""## §3.5–3.6　持股平方项 + 被解释变量

对应：
```stata
gen sharesowned2 = sharesowned^2
gen ln_tdc = log(TDC1)
```

`sharesowned` 单位是百分数(0–100)，`optionsvalue` 单位是千美元 ——
保持 Execucomp 原始单位，do 文件没有做任何缩放，这里也不做。
""")
code(r'''
exe["sharesowned"]  = pd.to_numeric(exe["sharesowned"],  errors="coerce")
exe["optionsvalue"] = pd.to_numeric(exe["optionsvalue"], errors="coerce")
exe["TDC1"]         = pd.to_numeric(exe["TDC1"],         errors="coerce")

print("TDC1 <= 0 的行数:", (exe["TDC1"] <= 0).sum(), "  <- 这些行 ln_tdc 会是缺失")

exe["sharesowned2"] = exe["sharesowned"] ** 2
exe["ln_tdc"]       = stata_log(exe["TDC1"])       # 同 LnAsset：log(0) 要是缺失

print(exe[["TDC1", "ln_tdc", "sharesowned", "optionsvalue"]].describe())
''')

# ----------------------------------------------------------------- 4
md(r"""## §4　合并两个数据集

对应：
```stata
merge 1:1 gvkey year using "data\execucomp_perforamance1.dta"
drop _merge
```

两个关键的语义差异：

1. **Stata 的 `merge` 默认保留全部三类观测**（`_merge=1` 只在主表 / `2` 只在副表 / `3` 两边都有）。
   do 文件只写了 `drop _merge`，**没有** `keep if _merge==3`。
   所以这里必须用 `how="outer"`，不能用 pandas 默认的 inner。
   匹配不上的行会带着一堆缺失值留在表里，最后在回归时被自动 listwise 剔除。
2. **`validate="1:1"`** 复刻 Stata 的 `merge 1:1` —— 任一边 key 不唯一就报错。

> `_merge` 这三个数字要写进你的 PDF。
""")
code(r'''
df = exe.merge(perf, on=["gvkey", "year"], how="outer",
               validate="1:1", indicator=True)

print(df["_merge"].value_counts())
print("\n合并后:", df.shape)

df = df.drop(columns="_merge")
''')

# ----------------------------------------------------------------- 5a
md(r"""## §4.5　样本流失诊断（可选，不改变任何结果）

do 文件里没有这一段，**它只打印、不改数据**，跑不跑都不影响回归结果。

作业模板表里 N = 8,263。如果你的 N 明显偏小，就用这一格定位是哪个变量把样本吃掉了：
回归是 listwise 剔除，**任何一个变量缺失，整行就没了**。

常见的三个元凶：
- `tenure_ceo` —— `becameceo` 日期解析失败（§3.4 会打印失败行数）
- `Volatility` —— `BS_VOLATILITY` 在 Execucomp 里本身就缺得多
- `lag_zROA` / `lag_zRstock` —— 需要连续年份，一家公司至少要有 3 个连续年度才能贡献一行
""")
code(r'''
REG = ["ln_tdc", "powerindex", "zROA", "zRstock", "lag_zROA", "lag_zRstock",
       "LnAsset", "Volatility", "sharesowned", "sharesowned2", "optionsvalue",
       "tenure_ceo", "tenure_ceo2"]

print("合并后总行数:", len(df))
print("\n各变量的非缺失行数：")
cnt = df[REG].notna().sum().sort_values()
print(cnt.to_string())

print("\n累计剔除（从最稀缺的变量开始逐个叠加）：")
keep = pd.Series(True, index=df.index)
for c in cnt.index:
    before = keep.sum()
    keep &= df[c].notna()
    print(f"  + {c:15s} {before:6d} -> {keep.sum():6d}   (少了 {before - keep.sum()})")

print("\n最终回归样本的年份分布：")
print(df.loc[keep, "year"].value_counts().sort_index().to_string())
print("\n最终样本公司数:", df.loc[keep, "gvkey"].nunique())

# 假如总资产完全不缺，N 最多能到多少 —— 决定值不值得重下数据
REG_noA = [c for c in REG if c != "LnAsset"]
print("\n不要求 LnAsset 时的样本上限:", df[REG_noA].notna().all(axis=1).sum(),
      "  (接近 8,263 → 缺口就是 ASSETS 造成的，值得重下)")
''')

md(r"""## §4.6　覆盖率诊断（可选，不改变任何结果）

§4.5 如果显示某个变量把样本砍掉一大块，用这一格判断它是**数据本身就缺**
（那老师用 Stata 跑也会掉同样的行），还是**格式问题**
（`to_numeric(errors="coerce")` 把某种写法全变成了 NaN，这种是可以修的）。

怎么读：
- **比例逐年不同**（早年低、后期高）→ Execucomp 的覆盖问题，无解，在 PDF 里说明即可
- **各年都差不多且都很低** → 格式问题，去看那一列的原始取值：`exe["sharesowned"].head(20)`
""")
code(r'''
print("exec (CEO only):", exe.shape, "| 年份", exe.year.min(), "-", exe.year.max(),
      "| 公司数", exe.gvkey.nunique())
print("perf           :", perf.shape, "| 年份", perf.year.min(), "-", perf.year.max(),
      "| 公司数", perf.gvkey.nunique())
print("共同 (gvkey,year) 对数:",
      len(set(map(tuple, exe[["gvkey", "year"]].to_numpy())) &
          set(map(tuple, perf[["gvkey", "year"]].to_numpy()))))

print("\nsharesowned 按年份的非缺失比例（exec）：")
print(exe.groupby("year")["sharesowned"].apply(lambda s: round(s.notna().mean(), 3)).to_string())

print("\nassets 按年份的非缺失比例（perf）：")
print(perf.groupby("year")["assets"].apply(lambda s: round(s.notna().mean(), 3)).to_string())
print("assets <= 0 的行数:", (perf["assets"] <= 0).sum())
''')

md(r"""## §5-a　第 (1) 列：Level effect
### Morse et al. (2011) Table II column (1)

对应：
```stata
reghdfe ln_tdc powerindex zROA zRstock lag_zROA lag_zRstock ///
        LnAsset Volatility sharesowned sharesowned2 optionsvalue tenure_ceo tenure_ceo2, ///
        absorb(gvkey year) vce(robust)
```

`pyfixest.feols` 就是 `reghdfe` 的对应物：
- `|` 后面 = `absorb()`，双向固定效应（公司 + 年份）
- `vcov="hetero"` = `vce(robust)`，异方差稳健标准误
- 缺失值的 listwise 剔除是自动的，和 Stata 一样
""")
code(r'''
CONTROLS = ("LnAsset + Volatility + sharesowned + sharesowned2 + "
            "optionsvalue + tenure_ceo + tenure_ceo2")

m1 = pf.feols(
    f"ln_tdc ~ powerindex + zROA + zRstock + lag_zROA + lag_zRstock + {CONTROLS}"
    " | gvkey + year",
    data=df, vcov="hetero",
)
m1.summary()
''')

# ----------------------------------------------------------------- 5b
md(r"""## §5-b　构造 Max 和交互项

对应：
```stata
gen max = 0
replace max = zROA    if zROA >  zRstock
replace max = zRstock if zROA <= zRstock
gen interaction = powerindex*max
```

`max = max(zROA, zRstock)`，即**「今年哪个业绩指标更好看，就取那个指标的标准化值」**。
它是**连续变量**，不是 0/1 哑变量。

**为什么可以直接写成一行 `max(axis=1)`：**
Stata 里 missing 被当作 +∞，所以
- `zROA` 缺失 → 第一个条件 `. > zRstock` 成立 → `max = zROA` = 缺失
- `zRstock` 缺失 → 第二个条件 `zROA <= .` 成立 → `max = zRstock` = 缺失

也就是"任一输入缺失，结果就缺失"。
pandas 的 `.max(axis=1)` 默认会**跳过** NaN，必须加 `skipna=False` 才等价。

（`gen max = 0` 那个初值在 Stata 里永远活不下来：两个条件互斥且穷尽。）
""")
code(r'''
df["max"] = df[["zROA", "zRstock"]].max(axis=1, skipna=False)
df["interaction"] = df["powerindex"] * df["max"]

# 自检：任一输入缺失时 max 必须是缺失
chk = df[["zROA", "zRstock", "max"]]
either_na = chk[["zROA", "zRstock"]].isna().any(axis=1)
assert chk.loc[either_na, "max"].isna().all(), "max 的缺失传播和 Stata 不一致"
print("max 缺失传播 OK")
print(df[["zROA", "zRstock", "max", "powerindex", "interaction"]].head(10))
''')

# ----------------------------------------------------------------- 5c
md(r"""## §5-c　第 (2) 列：Rigging effect
### Morse et al. (2011) Table III column (3)

对应：
```stata
reghdfe ln_tdc powerindex interaction zROA zRstock lag_zROA lag_zRstock ///
        <同样的控制变量>, absorb(gvkey year) vce(robust)
```

和第 (1) 列相比**只多了 `interaction` 一项，控制变量一个没少**。

两列的样本量会自动相同：`interaction` 缺失 ⟺ `max` 缺失 ⟺ `zROA` 或 `zRstock` 缺失，
而这两个在第 (1) 列已经是回归元，早就被剔掉了。所以不需要 `e(sample)` 之类的技巧。
""")
code(r'''
m2 = pf.feols(
    f"ln_tdc ~ powerindex + interaction + zROA + zRstock + lag_zROA + lag_zRstock + {CONTROLS}"
    " | gvkey + year",
    data=df, vcov="hetero",
)
m2.summary()
''')

# ----------------------------------------------------------------- 5d
md(r"""## §5-d　输出表格

对应：
```stata
outreg2 using "results\table1", excel replace ctitle(Table II column (1))  nocons dec(3) addtext(Firm FE, YES, Year FE, YES)
outreg2 using "results\table1", excel append  ctitle(Table III column (3)) nocons dec(3) addtext(Firm FE, YES, Year FE, YES)
```
""")
code(r'''
table1 = outreg2_like(
    [m1, m2],
    ["Table II column (1)", "Table III column (3)"],
    r("table1.xlsx"),
)
table1
''')

# ----------------------------------------------------------------- 5e
md(r"""## §5-e　存盘

对应 `save "data\execucomp_morse.dta", replace` + `clear all`。
""")
code(r'''
to_dta(df, p("execucomp_morse.dta"))
''')

# ----------------------------------------------------------------- 6a
md(r"""## §6-a　扩展题：读入气候风险敞口数据

对应：
```stata
import delimited "data\climatechage_exposure.csv"
keep gvkey year cc_expo_ew
duplicates drop gvkey year, force
```

最后那几行 `astype` 是**必须的**：Stata 的 merge 按数值匹配，而 `read_csv` 可能把
`gvkey` 读成 float（列里只要有一个缺失值就会）。
float 和 int64 两边**一条都匹配不上，而且不会报错**，只会安静地返回 0 个匹配。
""")
code(r'''
cc = pd.read_csv(p(CC_FILE))
print(cc.shape)
print(cc.columns.tolist())

cc = norm_cols(cc, {"GVKEY": "gvkey", "YEAR": "year", "CC_EXPO_EW": "cc_expo_ew"})
need(cc, ["gvkey", "year", "cc_expo_ew"], "climate 文件")

cc = cc[["gvkey", "year", "cc_expo_ew"]].copy()

cc["gvkey"]      = pd.to_numeric(cc["gvkey"],      errors="coerce")
cc["year"]       = pd.to_numeric(cc["year"],       errors="coerce")
cc["cc_expo_ew"] = pd.to_numeric(cc["cc_expo_ew"], errors="coerce")
cc = cc.dropna(subset=["gvkey", "year"])
cc[["gvkey", "year"]] = cc[["gvkey", "year"]].astype("int64")

cc = cc.drop_duplicates(subset=["gvkey", "year"], keep="first")   # duplicates drop ..., force
print("\n去重后:", cc.shape, "| 年份范围:", cc["year"].min(), "-", cc["year"].max())
''')

# ----------------------------------------------------------------- 6b
md(r"""## §6-b　与主样本合并

对应 `merge 1:1 gvkey year using "data\execucomp_morse.dta"`。

注意这次是**气候数据当主表**（和 §4 方向相反，但 1:1 的 outer merge 结果一样）。

do 文件这里**没有** `drop _merge`，所以 `_merge` 这一列会留在最终保存的
`extension_exercise.dta` 里 —— 照做，把它转成 Stata 的 1/2/3 编码。

气候数据从 2002 年开始、Execucomp 样本到 2005 年止，所以**实际重叠只有 2002–2005**，
这就是作业模板表里 N 只有 2,450 的原因，要在 PDF 里解释。
""")
code(r'''
# do 文件这里是从磁盘重读 execucomp_morse.dta；内存里的 df 内容完全相同，直接用
morse = df

ext = cc.merge(morse, on=["gvkey", "year"], how="outer",
               validate="1:1", indicator=True)
ext["_merge"] = ext["_merge"].map({"left_only": 1, "right_only": 2, "both": 3}).astype("int8")

print(ext["_merge"].value_counts().sort_index())
print("\n两边都有的年份分布:")
print(ext.loc[ext["_merge"] == 3, "year"].value_counts().sort_index())
''')

# ----------------------------------------------------------------- 6c
md(r"""## §6-c　扩展回归 + 出表 + 存盘

对应：
```stata
reghdfe ln_tdc cc_expo_ew powerindex interaction zROA zRstock lag_zROA lag_zRstock ///
        <控制变量>, absorb(gvkey year) vce(robust)
outreg2 using "results\table2", excel replace ctitle(Extension Exercise) nocons dec(3) addtext(Firm FE, YES, Year FE, YES)
save "data\extension_exercise.dta", replace
```

就是第 (2) 列的回归多加一个 `cc_expo_ew`。
""")
code(r'''
m3 = pf.feols(
    f"ln_tdc ~ cc_expo_ew + powerindex + interaction + zROA + zRstock + lag_zROA + lag_zRstock + {CONTROLS}"
    " | gvkey + year",
    data=ext, vcov="hetero",
)
m3.summary()
''')
code(r'''
table2 = outreg2_like([m3], ["Extension Exercise"], r("table2.xlsx"))
table2
''')
code(r'''
to_dta(ext, p("extension_exercise.dta"))
''')

md(r"""---

## 跑完了

产出文件：

| 路径 | 内容 |
|---|---|
| `data/execucomp_morse.dta` | 主回归数据集 |
| `data/extension_exercise.dta` | 扩展题数据集 |
| `results/table1.xlsx` | Table II col (1) + Table III col (3) |
| `results/table2.xlsx` | 扩展题 |

**注意：** 这份 notebook 严格照搬 `solution.do`，所以两个 `.dta` 里包含了
`_merge != 3` 的行和回归用不到的列。作业原文要求
"containing **only** those variables and data needed to estimate the regressions"，
交之前建议在 §5-e / §6-c 前面各加一句 `keep`/筛选 —— 这是 solution.do 本身没做的事。
""")

# --------------------------------------------------------------- build nb
cells = []
for kind, src in C:
    lines = src.split("\n")
    src_list = [l + "\n" for l in lines[:-1]] + [lines[-1]]
    if kind == "markdown":
        cells.append({"cell_type": "markdown", "metadata": {}, "source": src_list})
    else:
        cells.append({"cell_type": "code", "metadata": {}, "source": src_list,
                      "execution_count": None, "outputs": []})

nb = {
    "nbformat": 4, "nbformat_minor": 0,
    "metadata": {
        "colab": {"provenance": [], "toc_visible": True},
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
    },
    "cells": cells,
}

out = pathlib.Path("/home/user/claude-code-my-workflow/explorations/fidm-stata-replication/code/replication_fidm_colab.ipynb")
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1))
print("cells:", len(cells), "| bytes:", out.stat().st_size)
