# =============================================================================
# FIDM 2023-2024 Replication Assignment —— Python / Google Colab 版
#
# 严格对应 "Morse_et_al_replication_2023_-_solution.do"，一段一段照做，
# 不多做任何一步。每个 §编号 对应 do 文件里同一个 §编号。
#
# 用法：每个 "# %%" 之间的内容贴进 Colab 的一个 cell，从上往下依次运行。
# =============================================================================


# %% =========================================================================
# §0-a  Colab 环境准备
#
# do 文件里没有这一段（Stata 本地装好就能跑），但 Colab 每次开机都是空的，
# 必须先装 pyfixest —— 它是 Stata 里 reghdfe 的 Python 对应物，同样支持
# absorb() 多维固定效应和 vce(robust)。
# =============================================================================
!pip install -q pyfixest

import os
import numpy as np
import pandas as pd
import pyfixest as pf


# %% =========================================================================
# §0-b  对应 do 文件的  cd "C:\...\Replication_Assignment 2023"
#
# 把数据放进 Google Drive，挂载后 cd 过去。
# 目录结构要和 do 文件一致：
#   Replication_Assignment/
#     ├── data/     execucomp_executive.dta
#     │             execucomp_perforamance.dta
#     │             climatechage_exposure.csv
#     └── results/  (输出表格；do 文件里 outreg2 也是写到这里)
# =============================================================================
from google.colab import drive
drive.mount('/content/drive')

BASE = "/content/drive/MyDrive/Replication_Assignment"   # ← 改成你自己的路径
os.chdir(BASE)
os.makedirs("results", exist_ok=True)   # outreg2 不会自动建文件夹，Python 也不会

print(os.listdir("data"))


# %% =========================================================================
# §0-c  两个工具函数
#
# 这一段 do 文件里没有，但**不是多做的事**，而是补上 Stata 内建、Python 没有
# 的两个功能。不写这两个函数，下面的翻译就是错的。
#
# (1) stata_lag() —— 复刻 Stata 的  l.  滞后算子
#     Stata 的 l.x 是"同一个 gvkey 在 year-1 那一年的 x"。如果某公司缺 1995 年，
#     那 1996 年的 l.x 就是缺失。
#     pandas 的 .shift(1) 是"上一行"，遇到年份断档会错误地跨年取值。
#     所以必须把表按 year+1 错位后 merge 回去。
#
# (2) outreg2_like() —— 复刻 outreg2 的输出格式
#     系数带星号、标准误在括号里、底部附 N / R² / FE 行，导出成 Excel。
# =============================================================================

def stata_log(x):
    """复刻 Stata 的 log()：x <= 0 返回缺失。
    numpy 不一样：log(0) 给 -inf、log(负数) 给 nan。-inf 会污染回归，
    并让 to_stata 直接报 ValueError。"""
    x = pd.to_numeric(x, errors="coerce")
    return np.log(x.where(x > 0))


def no_inf(s):
    """复刻 Stata 的除法：分母为 0 时结果是缺失，而不是 ±inf。"""
    return pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan)


def stata_lag(df, cols, by="gvkey", t="year", n=1):
    """复刻 Stata 的 l. 算子：按 (by, t-n) 取值，该年份不存在就是缺失。"""
    lag = df[[by, t] + cols].copy()
    lag[t] = lag[t] + n                                   # 整体往后挪 n 年
    lag = lag.rename(columns={c: f"l{n}_{c}" for c in cols})
    return df.merge(lag, on=[by, t], how="left")


def outreg2_like(models, ctitles, path):
    """复刻 outreg2 ..., excel dec(3) addtext(Firm FE, YES, Year FE, YES)"""
    cols = {}
    for m, ct in zip(models, ctitles):
        t = m.tidy()                                      # pyfixest 的系数表
        col = {}
        for v in t.index:
            b, se, p = t.loc[v, "Estimate"], t.loc[v, "Std. Error"], t.loc[v, "Pr(>|t|)"]
            star = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""
            col[v]          = f"{b:.3f}{star}"            # 系数 + 显著性星号
            col[v + "_se"]  = f"({se:.3f})"               # 括号里的稳健标准误
        col["Observations"] = f"{int(getattr(m, '_N', np.nan)):,}"
        col["R-squared"]    = f"{getattr(m, '_r2', np.nan):.3f}"
        col["Firm FE"]      = "YES"
        col["Year FE"]      = "YES"
        cols[ct] = col
    out = pd.DataFrame(cols)
    out.to_excel(path)
    return out


# %% =========================================================================
# §1  读入公司财务数据
#     对应:  use "data\execucomp_perforamance.dta", clear
#
# 注意整份 do 文件的顺序：先处理 performance 文件，后处理 executive 文件。
# 这不是随意的——§2.3 的行业-年度标准化必须在"完整 firm-year 全样本"上算，
# 此时还没筛 CEO、还没 merge。顺序反了结果就变了。
# =============================================================================
perf = pd.read_stata("data/execucomp_perforamance.dta")

print(perf.shape)
print(perf.columns.tolist())      # 先确认变量名的大小写，再跑下一段


# %% =========================================================================
# §2.1  变量改名
#     对应:  rename GVKEY gvkey / rename ASSETS assets / ...
#
# WRDS 下载的 .dta 变量名是大写的，统一成小写。
# 注意 do 文件里 ROA 没有被 rename，全文一直用大写 ROA —— 这里照做。
# （如果上一段打印出来你的列名已经是小写，这一段会自动跳过不存在的键。）
# =============================================================================
perf = perf.rename(columns={
    "GVKEY":         "gvkey",
    "ASSETS":        "assets",
    "PRCCF":         "prccf",
    "YEAR":          "year",
    "BS_VOLATILITY": "bs_volatility",
    "SIC":           "sic",
    "AJEX":          "ajex",
})


# %% =========================================================================
# §2.2  设成面板数据
#     对应:  duplicates list gvkey year
#            destring gvkey, replace
#            xtset gvkey year
#
# · destring：WRDS 的 gvkey 是带前导零的字符串 "001004"，转成数字 1004。
#   这一步必须做，否则 §4 的 merge 两边 key 类型对不上，一条都匹配不上。
# · xtset：Stata 里如果 (gvkey, year) 不唯一会直接报错。Python 没有这个机制，
#   所以用 assert 手工复刻这个"断言"——do 文件能跑通，就说明它是唯一的。
# =============================================================================
perf["gvkey"] = pd.to_numeric(perf["gvkey"]).astype("int64")
perf["year"]  = pd.to_numeric(perf["year"]).astype("int64")

dup = perf.duplicated(subset=["gvkey", "year"]).sum()
print("duplicates on gvkey-year:", dup)
assert dup == 0, "gvkey-year 不唯一，Stata 的 xtset 在这里会报错"

perf = perf.sort_values(["gvkey", "year"]).reset_index(drop=True)


# %% =========================================================================
# §2.3-a  公司层面的控制变量
#     对应:  gen LnAsset = log(assets)
#            rename bs_volatility Volatility
#            gen Rstock = (prccf/ajex)/(l.prccf/l.ajex) - 1
#
# Rstock 是年度股票收益率。PRCCF 是未经拆股调整的年末收盘价，拆股当年会跳水；
# AJEX 是累计调整因子，PRCCF/AJEX 才是跨年可比的价格。
# 这里必须用上面的 stata_lag()，不能用 .shift(1)。
# （这是价格收益率，不含股息——因为作业没让下 TRS1YR。）
# =============================================================================
perf["LnAsset"] = stata_log(perf["assets"])      # Stata 的 log(0) 是缺失，不是 -inf
perf = perf.rename(columns={"bs_volatility": "Volatility"})

perf = stata_lag(perf, ["prccf", "ajex"])                 # 生成 l1_prccf, l1_ajex
perf["Rstock"] = no_inf(                          # Stata 的 x/0 是缺失，不是 inf
    (perf["prccf"] / perf["ajex"]) / (perf["l1_prccf"] / perf["l1_ajex"]) - 1
)


# %% =========================================================================
# §2.3-b  两位数行业代码
#     对应:  tostring sic, replace
#            replace sic = "0" + sic if strlen(sic) == 3
#            gen sic2 = substr(sic,1,2)
#
# SIC 是 4 位数字，但像 2711 这种存成数值后是 4 位、而 700 这种只有 3 位，
# 前面要补一个 "0" 变成 "0700"，否则取前两位会拿到 "70" 而不是 "07"。
# =============================================================================
perf["sic"] = perf["sic"].astype("Int64").astype(str)     # tostring
perf.loc[perf["sic"].str.len() == 3, "sic"] = "0" + perf["sic"]
perf["sic2"] = perf["sic"].str[:2]                        # substr(sic,1,2)


# %% =========================================================================
# §2.3-c  标准化的业绩指标  zROA / zRstock
#     对应:  sort sic2 year
#            by sic2 year: egen mean_sic2_year_ROA = mean(ROA)
#            by sic2 year: egen std_sic2_year_ROA  = sd(ROA)
#            gen zROA = (ROA - mean_sic2_year_ROA) / std_sic2_year_ROA
#
# 这是整个作业最关键的一步：把会计业绩(ROA)和市场业绩(Rstock)放到同一把尺子上，
# 基准组是「同一个两位数行业、同一年」的全部 Execucomp 公司。
# 这也解释了 SIC 为什么在下载清单上。
#
# pandas 的 transform("std") 默认 ddof=1，和 Stata 的 egen sd() 一致；
# 组内只有一个非缺失值时两者都给缺失。egen 和 transform 都自动跳过缺失值。
# =============================================================================
g = perf.groupby(["sic2", "year"])

perf["mean_sic2_year_ROA"]    = g["ROA"].transform("mean")
perf["std_sic2_year_ROA"]     = g["ROA"].transform("std")
perf["mean_sic2_year_Rstock"] = g["Rstock"].transform("mean")
perf["std_sic2_year_Rstock"]  = g["Rstock"].transform("std")

perf["zROA"]    = no_inf((perf["ROA"]    - perf["mean_sic2_year_ROA"])    / perf["std_sic2_year_ROA"])
perf["zRstock"] = no_inf((perf["Rstock"] - perf["mean_sic2_year_Rstock"]) / perf["std_sic2_year_Rstock"])


# %% =========================================================================
# §2.3-d  滞后一期的业绩指标
#     对应:  xtset gvkey year
#            gen lag_zROA    = l.zROA
#            gen lag_zRstock = l.zRstock
#
# 同样用 stata_lag()，按 (gvkey, year-1) 取值。
# 注意这一步是在 merge 之前、在全样本上做的，所以滞后项可以取到那些最终
# 进不了回归样本的年份 —— 这和 do 文件的行为一致。
# =============================================================================
perf = stata_lag(perf, ["zROA", "zRstock"])
perf = perf.rename(columns={"l1_zROA": "lag_zROA", "l1_zRstock": "lag_zRstock"})


# %% =========================================================================
# §2.4  存中间文件
#     对应:  save "data\execucomp_perforamance1.dta", replace
#            clear all
# =============================================================================
perf.to_stata("data/execucomp_perforamance1.dta", write_index=False, version=117)
print(perf.shape)


# %% =========================================================================
# §3  读入高管数据
#     对应:  use "data\execucomp_executive.dta", clear
# =============================================================================
exe = pd.read_stata("data/execucomp_executive.dta")

print(exe.shape)
print(exe.columns.tolist())


# %% =========================================================================
# §3.1  PowerIndex —— CEO 权力指数
#     对应:  gen lower_title = lower(TITLE)
#            gen powerindex = 0
#            replace powerindex = 1 if strpos(lower_title,"chairman")>0 | ...
#            replace powerindex = 2 if (chairman|chairwoman|chairperson) & president
#
# 这是一个 0/1/2 的序数变量，只看头衔兼任：
#     0 = 光杆 CEO
#     1 = CEO 兼董事长
#     2 = CEO 兼董事长 且 兼总裁
#
# 两个容易看漏的点：
#   · 只兼总裁、不兼董事长的仍然是 0（第二个 replace 要求 chairman 同时成立）
#   · tenure 和 sharesowned 不是指数的成分，它们只是控制变量
#
# .fillna("") 是在复刻 Stata：TITLE 缺失时 lower() 得到空串，strpos 返回 0，
# 于是 powerindex = 0。也就是说"没有头衔信息"被编码成"没有权力"。
# =============================================================================
lower_title = exe["TITLE"].fillna("").str.lower()

chair = (lower_title.str.contains("chairman",    regex=False) |
         lower_title.str.contains("chairwoman",  regex=False) |
         lower_title.str.contains("chairperson", regex=False))
pres  =  lower_title.str.contains("president",   regex=False)

exe["powerindex"] = 0
exe.loc[chair,          "powerindex"] = 1
exe.loc[chair & pres,   "powerindex"] = 2

print(exe["powerindex"].value_counts(dropna=False).sort_index())


# %% =========================================================================
# §3.2  变量改名
#     对应:  rename CEOANN ceoann / rename YEAR year / ...
#            destring gvkey, replace
#
# 同 §2.1。TDC1 保持大写（do 文件里也没改）。
# gvkey 同样要 destring，且类型必须和 perf 里的一模一样，否则 merge 匹配不上。
# =============================================================================
exe = exe.rename(columns={
    "CEOANN":                  "ceoann",
    "YEAR":                    "year",
    "SHROWN_EXCL_OPTS_PCT":    "sharesowned",
    "BECAMECEO":               "becameceo",
    "OPTION_AWARDS_BLK_VALUE": "optionsvalue",
    "GVKEY":                   "gvkey",
})

exe["gvkey"] = pd.to_numeric(exe["gvkey"]).astype("int64")
exe["year"]  = pd.to_numeric(exe["year"]).astype("int64")


# %% =========================================================================
# §3.3  只保留 CEO
#     对应:  gen CEO = 0
#            replace CEO = 1 if ceoann == "CEO"
#            keep if CEO == 1
#
# CEOANN 标记的是"该财年年末在任的 CEO"。
# 筛完之后每个 gvkey-year 应该只剩一行（下面 §4 的 validate="1:1" 会替你检查）。
# =============================================================================
exe = exe[exe["ceoann"] == "CEO"].copy()
print(exe.shape)


# %% =========================================================================
# §3.4  CEO 任期
#     对应:  gen tenure_ceo = year - year(becameceo)
#            replace tenure_ceo = . if year - year(becameceo) < 0
#            gen tenure_ceo2 = tenure_ceo^2
#
# becameceo 是日期型，read_stata 会读成 datetime，用 .dt.year 取年份。
# 负数是数据错误（上任日期晚于观测年份），置成缺失。
# =============================================================================
exe["becameceo"] = pd.to_datetime(exe["becameceo"], errors="coerce")

exe["tenure_ceo"] = exe["year"] - exe["becameceo"].dt.year
exe.loc[exe["tenure_ceo"] < 0, "tenure_ceo"] = np.nan
exe["tenure_ceo2"] = exe["tenure_ceo"] ** 2


# %% =========================================================================
# §3.5-3.6  持股平方项 + 被解释变量
#     对应:  gen sharesowned2 = sharesowned^2
#            rename option_awards_blk_value optionsvalue   (已在 §3.2 做完)
#            gen ln_tdc = log(TDC1)
#
# sharesowned 单位是百分数(0-100)，optionsvalue 单位是千美元 —— 保持 Execucomp
# 原始单位，do 文件没有做任何缩放，这里也不做。
# =============================================================================
exe["sharesowned2"] = exe["sharesowned"] ** 2
exe["ln_tdc"]       = stata_log(exe["TDC1"])      # 同 LnAsset


# %% =========================================================================
# §4  合并两个数据集
#     对应:  merge 1:1 gvkey year using "data\execucomp_perforamance1.dta"
#            drop _merge
#
# 两个关键的语义差异：
#  · Stata 的 merge 默认**保留全部三类**观测（_merge=1 只在主表 / 2 只在副表 /
#    3 两边都有），do 文件只写了 drop _merge，没有 keep if _merge==3。
#    所以这里必须用 how="outer"，不能用 pandas 默认的 inner。
#    匹配不上的行会带着一堆缺失值留在表里，最后在回归时被自动剔除。
#  · validate="1:1" 复刻 Stata 的 merge 1:1 —— 任一边 key 不唯一就报错。
# =============================================================================
df = exe.merge(perf, on=["gvkey", "year"], how="outer",
               validate="1:1", indicator=True)

print(df["_merge"].value_counts())        # 这三个数字写进你的 PDF
df = df.drop(columns="_merge")


# %% =========================================================================
# §5-a  第 (1) 列：Level effect —— Morse et al. Table II column (1)
#     对应:  reghdfe ln_tdc powerindex zROA zRstock lag_zROA lag_zRstock
#                    LnAsset Volatility sharesowned sharesowned2 optionsvalue
#                    tenure_ceo tenure_ceo2, absorb(gvkey year) vce(robust)
#
# pyfixest 的 feols 就是 reghdfe 的对应物：
#     "|" 后面 = absorb()           双向固定效应（公司 + 年份）
#     vcov="hetero" = vce(robust)   异方差稳健标准误
# 缺失值的 listwise 剔除是自动的，和 Stata 一样。
# =============================================================================
CONTROLS = "LnAsset + Volatility + sharesowned + sharesowned2 + optionsvalue + tenure_ceo + tenure_ceo2"

m1 = pf.feols(
    f"ln_tdc ~ powerindex + zROA + zRstock + lag_zROA + lag_zRstock + {CONTROLS} | gvkey + year",
    data=df, vcov="hetero",
)
m1.summary()


# %% =========================================================================
# §5-b  构造 Max 和交互项
#     对应:  gen max = 0
#            replace max = zROA    if zROA >  zRstock
#            replace max = zRstock if zROA <= zRstock
#            gen interaction = powerindex*max
#
# max = max(zROA, zRstock)，即「今年哪个业绩指标更好看，就取那个指标的标准化值」。
# 它是**连续变量**，不是 0/1 哑变量。
#
# 为什么可以直接写成一行 max(axis=1)：
#   Stata 里 missing 被当作 +∞，所以
#     zROA 缺失   → 第一个条件成立 → max = zROA   = 缺失
#     zRstock 缺失 → 第二个条件成立 → max = zRstock = 缺失
#   也就是"任一输入缺失，结果就缺失"。
#   pandas 的 .max(axis=1) 默认会跳过 NaN，必须加 skipna=False 才等价。
#   （gen max = 0 那个初值在 Stata 里永远活不下来：两个条件互斥且穷尽。）
# =============================================================================
df["max"] = df[["zROA", "zRstock"]].max(axis=1, skipna=False)
df["interaction"] = df["powerindex"] * df["max"]


# %% =========================================================================
# §5-c  第 (2) 列：Rigging effect —— Morse et al. Table III column (3)
#     对应:  reghdfe ln_tdc powerindex interaction zROA zRstock lag_zROA
#                    lag_zRstock <同样的控制变量>, absorb(gvkey year) vce(robust)
#
# 和第 (1) 列相比只多了 interaction 一项，控制变量一个没少。
# 两列的样本量会自动相同：interaction 缺失 ⟺ max 缺失 ⟺ zROA 或 zRstock 缺失，
# 而这两个在第 (1) 列已经是回归元，早就被剔掉了。
# =============================================================================
m2 = pf.feols(
    f"ln_tdc ~ powerindex + interaction + zROA + zRstock + lag_zROA + lag_zRstock + {CONTROLS} | gvkey + year",
    data=df, vcov="hetero",
)
m2.summary()


# %% =========================================================================
# §5-d  输出表格
#     对应:  outreg2 using "results\table1", excel replace/append
#                    ctitle(...) nocons dec(3) addtext(Firm FE, YES, Year FE, YES)
# =============================================================================
table1 = outreg2_like(
    [m1, m2],
    ["Table II column (1)", "Table III column (3)"],
    "results/table1.xlsx",
)
table1


# %% =========================================================================
# §5-e  存盘
#     对应:  save "data\execucomp_morse.dta", replace
#            clear all
#
# to_stata 不接受 datetime 列，所以要用 convert_dates 告诉它哪些是日期
# （becameceo）。Stata 的 %td 对应 "td"。
# =============================================================================
date_cols = {c: "td" for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])}
df.to_stata("data/execucomp_morse.dta", write_index=False, version=117,
            convert_dates=date_cols)
print(df.shape)


# %% =========================================================================
# §6-a  扩展题：读入气候风险敞口数据
#     对应:  import delimited "data\climatechage_exposure.csv"
#            keep gvkey year cc_expo_ew
#            duplicates drop gvkey year, force
#
# 最后那几行 astype 是必须的：Stata 的 merge 按数值匹配，而 read_csv 可能把
# gvkey 读成 float（只要列里有一个缺失值就会）。float 和 int64 两边
# **一条都匹配不上，而且不会报错**，只会安静地返回 0 个匹配。
# =============================================================================
cc = pd.read_csv("data/climatechage_exposure.csv")
cc = cc[["gvkey", "year", "cc_expo_ew"]]

cc["gvkey"] = pd.to_numeric(cc["gvkey"], errors="coerce")
cc["year"]  = pd.to_numeric(cc["year"],  errors="coerce")
cc = cc.dropna(subset=["gvkey", "year"])
cc[["gvkey", "year"]] = cc[["gvkey", "year"]].astype("int64")

cc = cc.drop_duplicates(subset=["gvkey", "year"], keep="first")   # force
print(cc.shape)


# %% =========================================================================
# §6-b  与主样本合并
#     对应:  merge 1:1 gvkey year using "data\execucomp_morse.dta"
#
# 注意这次是气候数据当主表（和 §4 方向相反，但 1:1 的 outer merge 结果一样）。
# do 文件这里**没有** drop _merge，所以 _merge 这一列会留在最终保存的
# extension_exercise.dta 里 —— 照做，把它转成 Stata 的 1/2/3 编码。
# 气候数据从 2002 年开始、Execucomp 样本到 2005 年止，所以实际重叠只有 2002-2005。
# =============================================================================
morse = pd.read_stata("data/execucomp_morse.dta")

ext = cc.merge(morse, on=["gvkey", "year"], how="outer",
               validate="1:1", indicator=True)
ext["_merge"] = ext["_merge"].map({"left_only": 1, "right_only": 2, "both": 3}).astype("int8")

print(ext["_merge"].value_counts().sort_index())


# %% =========================================================================
# §6-c  扩展回归 + 出表 + 存盘
#     对应:  reghdfe ln_tdc cc_expo_ew powerindex interaction zROA zRstock
#                    lag_zROA lag_zRstock <控制变量>, absorb(gvkey year) vce(robust)
#            outreg2 using "results\table2", excel replace ...
#            save "data\extension_exercise.dta", replace
#
# 就是第 (2) 列的回归多加一个 cc_expo_ew。
# =============================================================================
m3 = pf.feols(
    f"ln_tdc ~ cc_expo_ew + powerindex + interaction + zROA + zRstock + lag_zROA + lag_zRstock + {CONTROLS} | gvkey + year",
    data=ext, vcov="hetero",
)
m3.summary()

table2 = outreg2_like([m3], ["Extension Exercise"], "results/table2.xlsx")

date_cols = {c: "td" for c in ext.columns if pd.api.types.is_datetime64_any_dtype(ext[c])}
ext.to_stata("data/extension_exercise.dta", write_index=False, version=117,
             convert_dates=date_cols)
print(ext.shape)

# =============================================================================
# End
# =============================================================================
