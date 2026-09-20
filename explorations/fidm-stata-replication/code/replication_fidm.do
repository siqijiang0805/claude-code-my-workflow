*===============================================================================
* FIDM 2023-2024  --  REPLICATION ASSIGNMENT
*
* Purpose : Replicate the level effect (Morse, Nanda & Seru 2011, Table II col 1)
*           and the rigging effect (Table III col 3), and run the climate-change
*           extension.
* Input   : data/execucomp_executive.dta      (Execucomp Annual Compensation, 1992-2005)
*           data/execucomp_perforamance.dta   (Execucomp Company Financial, 1992-2005)
*                                             [spelling as required by the instruction]
*           data/firmyear_score_2021Q4_Version_2022_Nov_22.csv   (OSF, Sautner et al. 2023)
* Output  : data/execucomp_morse.dta
*           data/extension_exercise.dta
*           result/table_main.rtf
*           result/table_extension.rtf
* Authors : [GROUP MEMBER NAMES]
* Date    : [DATE]
*===============================================================================

*-------------------------------------------------------------------------------
* 0. SET-UP
*-------------------------------------------------------------------------------
clear all
set more off
version 17                      // adapt to your Stata version

* --- working directory: the ONLY machine-specific line in this do file ---------
cd "[YOUR PATH]/Stata workshop"          // Windows: cd "C:\Users\...\Stata workshop"

capture mkdir "result"
capture mkdir "temp"

* --- packages (workshop Exercise: ssc install) ---------------------------------
capture which winsor2   | ssc install winsor2, replace
capture which outreg2   | ssc install outreg2, replace
capture which unique    | ssc install unique, replace
capture which reghdfe   | ssc install reghdfe, replace
capture which ftools    | ssc install ftools, replace   // reghdfe dependency

* --- log -----------------------------------------------------------------------
capture log close
log using "result/replication_log.smcl", replace


*===============================================================================
* 1. CLEAN THE EXECUTIVE FILE  (execucomp_executive.dta)
*    Level = executive-year.  Goal: one row per CEO-firm-year.
*===============================================================================
use "data/execucomp_executive.dta", clear

describe                         // ALWAYS look at types first (string vs numeric)
codebook gvkey year ceoann, compact

* --- 1.1 keep CEOs only --------------------------------------------------------
* CEOANN == "CEO" flags the person who was CEO at fiscal year end.
tab ceoann, missing
keep if ceoann == "CEO"

* --- 1.2 make gvkey a clean, CONSISTENT type ------------------------------------
* This is the single most common source of failed merges. Pick ONE convention
* and use it in every dataset in this do file. Here: numeric.
capture confirm string variable gvkey
if !_rc destring gvkey, replace
destring year, replace force          // no-op if already numeric

* --- 1.3 the panel must be unique at gvkey-year ---------------------------------
duplicates report gvkey year
duplicates list   gvkey year          // INSPECT before dropping (workshop Ex.5)
* Duplicates arise when Execucomp flags two CEOs in one fiscal year (turnover).
* Decide and DOCUMENT your rule, e.g. keep the one with the higher TDC1:
bysort gvkey year (tdc1): keep if _n == _N
isid gvkey year                       // hard stop if still not unique

* --- 1.4 dependent variable -----------------------------------------------------
* TDC1 = total compensation (salary + bonus + other annual + LTIP + option grants)
drop if missing(tdc1) | tdc1 <= 0     // log is undefined otherwise
gen double LnTDC = log(tdc1)
label variable LnTDC "Ln(CEO total compensation, TDC1)"

* --- 1.5 CEO tenure  (from BECAMECEO) -------------------------------------------
* BECAMECEO is a daily date in the .dta. If WRDS gave you a string, convert first.
capture confirm string variable becameceo
if !_rc {
    gen becameceo_d = date(becameceo, "YMD")          // check the actual format!
    format becameceo_d %td
    drop becameceo
    rename becameceo_d becameceo
}
gen ceo_start_year = year(becameceo)
gen Tenure         = year - ceo_start_year
replace Tenure = .  if Tenure < 0                      // data errors
gen Tenure_squared = Tenure^2
label variable Tenure         "Years since becoming CEO"
label variable Tenure_squared "Tenure squared"

* --- 1.6 CEO ownership ----------------------------------------------------------
* SHROWN_EXCL_OPTS_PCT = % of total shares owned, excluding options.
rename shrown_excl_opts_pct Sharesowned
gen Sharesowned_squared = Sharesowned^2
label variable Sharesowned         "% of shares owned, excl. options"
label variable Sharesowned_squared "Shares owned squared"

* --- 1.7 value of option grants --------------------------------------------------
rename option_awards_blk_value Optionsvalue
label variable Optionsvalue "Black-Scholes value of options granted ($000)"
* NOTE ON UNITS: Execucomp reports this in $thousands. Whatever scaling you use
* (raw, /1000, or /tdc1), state it in the PDF -- it drives the coefficient size.

* --- 1.8 title-based power components (from TITLE) --------------------------------
gen title_l = lower(title)                              // workshop Ex.12: lower()
gen byte d_chairman  = (strpos(title_l, "chairman") > 0 | strpos(title_l, "chmn") > 0)
gen byte d_president = (strpos(title_l, "pres") > 0)
gen byte d_founder   = (strpos(title_l, "founder") > 0)
replace d_chairman  = . if missing(title)
replace d_president = . if missing(title)
replace d_founder   = . if missing(title)
* SANITY CHECK the string matching before you trust it:
tab title if d_chairman == 1, sort
tab title if d_chairman == 0 & d_president == 0, sort

keep gvkey year execid co_per_rol exec_fullname LnTDC tdc1 ///
     Tenure Tenure_squared Sharesowned Sharesowned_squared Optionsvalue ///
     d_chairman d_president d_founder
compress
save "temp/exec_clean.dta", replace


*===============================================================================
* 2. CLEAN THE PERFORMANCE FILE  (execucomp_perforamance.dta)
*    Level = firm-year.
*===============================================================================
use "data/execucomp_perforamance.dta", clear
describe

capture confirm string variable gvkey
if !_rc destring gvkey, replace
destring year, replace force

duplicates report gvkey year
duplicates drop  gvkey year, force
isid gvkey year

* --- 2.1 firm size ----------------------------------------------------------------
drop if missing(assets) | assets <= 0
gen double LnAsset = log(assets)
label variable LnAsset "Ln(total assets)"

* --- 2.2 stock return volatility ---------------------------------------------------
rename bs_volatility Volatility
label variable Volatility "60-month Black-Scholes volatility"

* --- 2.3 ANNUAL STOCK RETURN -- this is why AJEX was on the download list ----------
* PRCCF is the raw fiscal-year-end close price; it jumps on splits.
* AJEX is the cumulative adjustment factor. PRCCF/AJEX is the split-adjusted price.
xtset gvkey year
gen double prc_adj = prccf / ajex
gen double Rstock  = prc_adj / L.prc_adj - 1
label variable Rstock "Fiscal-year stock return (split-adjusted, ex-dividend)"
* CAVEAT to state in the PDF: this is a price return; it excludes dividends,
* because the instruction did not ask you to download TRS1YR.

* --- 2.4 industry code -------------------------------------------------------------
* SIC is on the download list for a reason -- see Section 4.2 and 5.
capture confirm string variable sic
if _rc {
    tostring sic, gen(sic_str) format(%04.0f)
}
else {
    gen sic_str = sic
}
gen num_digits_sic = strlen(sic_str)          // workshop Ex.12
tab num_digits_sic
gen sic2 = substr(sic_str, 1, 2)
destring sic2, replace
label variable sic2 "2-digit SIC industry"

keep gvkey year LnAsset assets Volatility Rstock roa sic sic2 prccf ajex
compress
save "temp/perf_clean.dta", replace


*===============================================================================
* 3. MERGE  (instruction: merge on gvkey and year)
*===============================================================================
use "temp/exec_clean.dta", clear
merge 1:1 gvkey year using "temp/perf_clean.dta"

tab _merge                    // report these counts in the PDF
keep if _merge == 3           // workshop Ex.19
drop _merge

xtset gvkey year


*===============================================================================
* 4. CONSTRUCT THE ANALYSIS VARIABLES
*===============================================================================

*-------------------------------------------------------------------------------
* 4.1 Winsorize continuous variables at 1% / 99%   (workshop Ex.9)
*-------------------------------------------------------------------------------
winsor2 roa Rstock LnAsset Volatility Sharesowned Optionsvalue Tenure, ///
        cuts(1 99) replace
* Re-build the squared terms AFTER winsorizing the levels:
replace Sharesowned_squared = Sharesowned^2
replace Tenure_squared      = Tenure^2

*-------------------------------------------------------------------------------
* 4.2 zROA and zRstock  --  standardised performance measures
*
* >>> THE SINGLE MOST CONSEQUENTIAL CHOICE IN THIS ASSIGNMENT <<<
* The two measures must be on a COMMON scale, otherwise "which measure looks
* better this year" (the Max variable) is meaningless. Read the notes to
* Table II / Table III in Morse et al. (2011) and pick ONE benchmark group,
* then state it in the PDF. Three defensible variants, coded below:
*   A) by year                 -- "relative to all firms this year"
*   B) by sic2-year            -- "relative to industry peers this year"
*   C) by firm (over time)     -- "relative to the firm's own history"
*-------------------------------------------------------------------------------

* ---- VARIANT A: by year (uncomment the variant you choose) --------------------
bysort year: egen double m_roa = mean(roa)
bysort year: egen double s_roa = sd(roa)
gen double zROA = (roa - m_roa) / s_roa

bysort year: egen double m_rst = mean(Rstock)
bysort year: egen double s_rst = sd(Rstock)
gen double zRstock = (Rstock - m_rst) / s_rst

/*  ---- VARIANT B: by industry-year (workshop Ex.13: bysort ... : egen) --------
bysort sic2 year: egen double m_roa = mean(roa)
bysort sic2 year: egen double s_roa = sd(roa)
gen double zROA = (roa - m_roa) / s_roa
bysort sic2 year: egen double m_rst = mean(Rstock)
bysort sic2 year: egen double s_rst = sd(Rstock)
gen double zRstock = (Rstock - m_rst) / s_rst
*/

/*  ---- VARIANT C: by firm over time -------------------------------------------
bysort gvkey: egen double m_roa = mean(roa)
bysort gvkey: egen double s_roa = sd(roa)
gen double zROA = (roa - m_roa) / s_roa
bysort gvkey: egen double m_rst = mean(Rstock)
bysort gvkey: egen double s_rst = sd(Rstock)
gen double zRstock = (Rstock - m_rst) / s_rst
*/

drop m_roa s_roa m_rst s_rst
label variable zROA     "Standardised ROA"
label variable zRstock  "Standardised stock return"

* --- lagged performance (workshop Ex.15: L. operator; requires xtset) -----------
xtset gvkey year
gen double lag_zROA    = L.zROA
gen double lag_zRstock = L.zRstock
label variable lag_zROA    "Lagged standardised ROA"
label variable lag_zRstock "Lagged standardised stock return"

*-------------------------------------------------------------------------------
* 4.3 Max -- the "more favourable" performance measure
*     = 1 when the standardised stock return looks better than standardised ROA
*-------------------------------------------------------------------------------
gen byte Max = (zRstock > zROA) if !missing(zRstock, zROA)
label variable Max "1 if zRstock > zROA (more favourable measure)"
tab Max                       // should be roughly 50/50; if not, re-check 4.2

*-------------------------------------------------------------------------------
* 4.4 PowerIndex
*
* >>> VERIFY THE COMPONENT LIST against the Data section of Morse et al. (2011).
* The four candidates below are exactly what the downloaded variables allow
* (TITLE -> chairman/president; BECAMECEO -> tenure; SHROWN_EXCL_OPTS_PCT ->
* ownership). Adjust the list, and the cut-offs, to match the paper.
*-------------------------------------------------------------------------------
bysort year: egen double p50_tenure = median(Tenure)
bysort year: egen double p50_own    = median(Sharesowned)

gen byte d_tenure_high = (Tenure      > p50_tenure) if !missing(Tenure)
gen byte d_own_high    = (Sharesowned > p50_own)    if !missing(Sharesowned)

egen byte PowerIndex = rowtotal(d_chairman d_president d_tenure_high d_own_high)
replace  PowerIndex = . if missing(d_chairman, d_president, d_tenure_high, d_own_high)
label variable PowerIndex "CEO power index (0-4)"
tab PowerIndex, missing        // report this distribution in the PDF

drop p50_tenure p50_own

* --- the interaction term -------------------------------------------------------
gen double MaxPowerIndex = Max * PowerIndex
label variable MaxPowerIndex "Max x PowerIndex"

* --- numeric firm id for the fixed effects ---------------------------------------
egen long firm_id = group(gvkey)


*===============================================================================
* 5. SAMPLE SCREENS
*===============================================================================
keep if inrange(year, 1992, 2005)

* Financials (SIC 6000-6999) and utilities (SIC 4900-4949) are routinely excluded
* in the executive-pay literature because their accounting and regulation differ.
* CHECK whether Morse et al. (2011) do this; if yes, uncomment:
* drop if inrange(sic, 6000, 6999)
* drop if inrange(sic, 4900, 4949)

* Listwise deletion so BOTH columns run on an identical sample:
egen byte nmiss = rowmiss(LnTDC PowerIndex zROA zRstock lag_zROA lag_zRstock ///
                          LnAsset Volatility Sharesowned Sharesowned_squared ///
                          Optionsvalue Tenure Tenure_squared Max)
keep if nmiss == 0
drop nmiss

unique gvkey                    // number of firms
unique gvkey year               // should equal _N
count                           // target order of magnitude: ~8,000 obs

* --- descriptive statistics for the PDF (workshop Ex.7) ---------------------------
tabstat LnTDC PowerIndex Max zROA zRstock lag_zROA lag_zRstock LnAsset ///
        Volatility Sharesowned Optionsvalue Tenure, ///
        stat(N mean sd min p25 median p75 max) columns(statistics)


*===============================================================================
* 6. REGRESSIONS  (workshop Ex.17 / Ex.18)
*===============================================================================
global CONTROLS LnAsset Volatility Sharesowned Sharesowned_squared ///
                Optionsvalue Tenure Tenure_squared

* --- Column (1): LEVEL EFFECT  = Morse et al. Table II, column (1) ---------------
reghdfe LnTDC PowerIndex zROA zRstock lag_zROA lag_zRstock $CONTROLS, ///
        absorb(firm_id year) vce(cluster firm_id)
estimates store col1
gen byte esample = e(sample)       // lock the sample so column (2) matches N

outreg2 using "result/table_main.rtf", replace word ///
    label nocons se bdec(3) sdec(3) ///
    addstat("R-squared", e(r2)) ///
    addtext("Firm FE", "YES", "Year FE", "YES") ///
    ctitle("Table II column (1)") ///
    title("Table 1. CEO power and CEO compensation, Execucomp 1992-2005")

* --- Column (2): RIGGING EFFECT = Morse et al. Table III, column (3) -------------
* NOTE: equation (2) in the instruction contains X'b, but the template table
* leaves the control rows blank in column (2). Decide, run it, and flag the
* discrepancy in the "issues for the grader" section of the PDF.
reghdfe LnTDC PowerIndex MaxPowerIndex zROA zRstock lag_zROA lag_zRstock ///
        $CONTROLS if esample, ///
        absorb(firm_id year) vce(cluster firm_id)
estimates store col2

outreg2 using "result/table_main.rtf", append word ///
    label nocons se bdec(3) sdec(3) ///
    addstat("R-squared", e(r2)) ///
    addtext("Firm FE", "YES", "Year FE", "YES") ///
    ctitle("Table III column (3)")

* Variant to consider and document: include the main effect of Max as well.
* reghdfe LnTDC PowerIndex Max MaxPowerIndex zROA zRstock lag_zROA lag_zRstock ///
*         $CONTROLS if esample, absorb(firm_id year) vce(cluster firm_id)


*===============================================================================
* 7. SAVE execucomp_morse.dta
*    "containing ONLY those variables and data needed to estimate the regressions"
*===============================================================================
keep gvkey year firm_id LnTDC PowerIndex Max MaxPowerIndex ///
     zROA zRstock lag_zROA lag_zRstock $CONTROLS
order gvkey year firm_id LnTDC PowerIndex Max MaxPowerIndex ///
      zROA zRstock lag_zROA lag_zRstock
compress
save "data/execucomp_morse.dta", replace


*===============================================================================
* 8. EXTENSION: firm-level climate change exposure (Sautner et al. 2023)
*===============================================================================

* --- 8.1 import the OSF file ------------------------------------------------------
import delimited "data/firmyear_score_2021Q4_Version_2022_Nov_22.csv", ///
       clear varnames(1) case(lower)
describe

keep gvkey year cc_expo_ew

* gvkey MUST end up the same type as in execucomp_morse.dta (numeric here):
capture confirm string variable gvkey
if !_rc destring gvkey, replace force
destring year cc_expo_ew, replace force
drop if missing(gvkey, year)

duplicates report gvkey year
duplicates drop  gvkey year, force
isid gvkey year

rename cc_expo_ew ClimateChange_Exposure
label variable ClimateChange_Exposure "Firm-level climate change exposure (cc_expo_ew)"
save "temp/climate_clean.dta", replace

* --- 8.2 merge onto the replication sample -----------------------------------------
use "data/execucomp_morse.dta", clear
merge 1:1 gvkey year using "temp/climate_clean.dta"
tab _merge
keep if _merge == 3
drop _merge
* Coverage note for the PDF: the OSF data start in 2002 and the Execucomp sample
* ends in 2005, so the extension sample is effectively 2002-2005 only.
tab year

* --- 8.3 re-run the rigging regression with the new regressor ----------------------
xtset firm_id year
reghdfe LnTDC ClimateChange_Exposure PowerIndex MaxPowerIndex ///
        zROA zRstock lag_zROA lag_zRstock $CONTROLS, ///
        absorb(firm_id year) vce(cluster firm_id)
estimates store col3

outreg2 using "result/table_extension.rtf", replace word ///
    label nocons se bdec(3) sdec(3) ///
    addstat("R-squared", e(r2)) ///
    addtext("Firm FE", "YES", "Year FE", "YES") ///
    ctitle("Extension Exercise") ///
    title("Table 2. Climate change exposure and CEO compensation")

* --- 8.4 save ------------------------------------------------------------------------
compress
save "data/extension_exercise.dta", replace

log close

*===============================================================================
* END OF DO FILE
*===============================================================================
