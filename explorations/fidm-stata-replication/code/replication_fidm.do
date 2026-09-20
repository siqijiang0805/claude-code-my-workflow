*===============================================================================
* FIDM 2023-2024  --  REPLICATION ASSIGNMENT
*
* Purpose : Replicate the level effect (Morse, Nanda & Seru 2011, Table II col 1)
*           and the rigging effect (Table III col 3), plus the climate-change
*           extension (Sautner et al. 2023).
*
* Input   : data/execucomp_executive.dta       Execucomp Annual Compensation, 1992-2005
*           data/execucomp_perforamance.dta    Execucomp Company Financial, 1992-2005
*                                              [spelling as required by the instruction]
*           data/climatechage_exposure.csv     OSF firmyear_score_2021Q4_..., renamed
* Output  : data/execucomp_morse.dta
*           data/extension_exercise.dta
*           results/table1.xls, results/table2.xls
*
* All variable definitions follow the official solution
* (code/official_solution.do). Lines marked [SUBMISSION FIX] are additions the
* assignment text requires but the official solution omits; lines marked
* [DISCUSS] are judgement calls to write up in the 2-page PDF.
*
* Authors : [GROUP MEMBER NAMES]
* Date    : [DATE]
*===============================================================================

clear all
set more off

*-------------------------------------------------------------------------------
* 0) Working directory -- the ONLY machine-specific line in this do file
*-------------------------------------------------------------------------------
cd "[YOUR PATH]/Replication_Assignment"
* Windows: cd "C:\Users\...\Replication_Assignment"
* Mac    : cd "/Users/.../Replication_Assignment"      and use "/" in all paths below

capture mkdir "results"        // outreg2 errors out if this folder does not exist

* Packages used: winsor2 is NOT needed (the solution does not winsorize).
capture which reghdfe  | ssc install reghdfe, replace
capture which ftools   | ssc install ftools,  replace
capture which outreg2  | ssc install outreg2, replace


*===============================================================================
* 1-2) COMPANY FINANCIAL FILE
*
* Done FIRST and on the FULL firm-year panel, before any CEO filter and before
* the merge. That matters: the industry-year benchmark for the z-scores is all
* Execucomp firms in that sic2-year, and the lags can reach back into firm-years
* that never enter the regression sample.
*===============================================================================
use "data/execucomp_perforamance.dta", clear

*--- 2.1) WRDS ships the .dta with UPPERCASE names; standardise them ------------
rename GVKEY         gvkey
rename ASSETS        assets
rename PRCCF         prccf
rename YEAR          year
rename BS_VOLATILITY bs_volatility
rename SIC           sic
rename AJEX          ajex
* NOTE: ROA is deliberately left uppercase and used as ROA throughout.

*--- 2.2) panel set-up -----------------------------------------------------------
duplicates list gvkey year        // inspect only; the file should already be unique
destring gvkey, replace           // "001004" (string, leading zeros) -> 1004 (numeric)
xtset gvkey year

*--- 2.3) firm-level variables ----------------------------------------------------
gen LnAsset = log(assets)
rename bs_volatility Volatility

* Annual stock return. PRCCF is the RAW fiscal-year-end close, which jumps on
* splits; AJEX is the cumulative adjustment factor, so PRCCF/AJEX is comparable
* across years. [DISCUSS] This is a PRICE return: it excludes dividends, because
* the instruction did not ask for TRS1YR.
gen Rstock = (prccf/ajex)/(l.prccf/l.ajex) - 1

* 2-digit SIC industry
tostring sic, replace
replace sic = "0" + sic if strlen(sic) == 3     // pad 3-digit codes to 4
gen sic2 = substr(sic,1,2)

* --- STANDARDISED PERFORMANCE: benchmark group is sic2 x year -------------------
sort sic2 year
by sic2 year: egen mean_sic2_year_ROA    = mean(ROA)
by sic2 year: egen std_sic2_year_ROA     = sd(ROA)
by sic2 year: egen mean_sic2_year_Rstock = mean(Rstock)
by sic2 year: egen std_sic2_year_Rstock  = sd(Rstock)

gen zROA    = (ROA    - mean_sic2_year_ROA)    / std_sic2_year_ROA
gen zRstock = (Rstock - mean_sic2_year_Rstock) / std_sic2_year_Rstock

label variable zROA    "Standardised ROA (sic2-year)"
label variable zRstock "Standardised stock return (sic2-year)"

xtset gvkey year
gen lag_zROA    = l.zROA
gen lag_zRstock = l.zRstock

save "data/execucomp_perforamance1.dta", replace
clear all


*===============================================================================
* 3) EXECUTIVE FILE
*===============================================================================
use "data/execucomp_executive.dta", clear

*-------------------------------------------------------------------------------
* 3.1) POWER INDEX -- an ordinal 0/1/2 title-concentration measure
*      0 = CEO only
*      1 = CEO who is also chairman
*      2 = CEO who is also chairman AND president
*      Note: president WITHOUT chairman stays at 0 (the second replace requires
*      the chairman condition as well).
*      Tenure and ownership are NOT components -- they are controls only.
*-------------------------------------------------------------------------------
gen lower_title = lower(TITLE)

gen powerindex = 0
replace powerindex = 1 if strpos(lower_title,"chairman")    > 0 ///
                        | strpos(lower_title,"chairwoman")  > 0 ///
                        | strpos(lower_title,"chairperson") > 0

replace powerindex = 2 if (strpos(lower_title,"chairman")    > 0 ///
                        |  strpos(lower_title,"chairwoman")  > 0 ///
                        |  strpos(lower_title,"chairperson") > 0) ///
                        & strpos(lower_title,"president") > 0

* [DISCUSS] A missing TITLE gives lower_title == "", strpos() == 0, hence
* powerindex == 0. "No title information" is therefore coded as "no power".
* Quantify it for the PDF:
count if missing(TITLE)
tab powerindex, missing
* Sanity-check the string matching before trusting it:
tab TITLE if powerindex == 2, sort

*--- 3.2) rename the remaining variables ------------------------------------------
rename CEOANN                  ceoann
rename YEAR                    year
rename SHROWN_EXCL_OPTS_PCT    sharesowned      // % of shares owned, excl. options
rename BECAMECEO               becameceo
rename OPTION_AWARDS_BLK_VALUE optionsvalue     // Black-Scholes value, $ thousands
rename GVKEY                   gvkey
destring gvkey, replace                          // same type as the other file

*--- 3.3) keep CEOs only ------------------------------------------------------------
keep if ceoann == "CEO"

*--- 3.4) CEO tenure ---------------------------------------------------------------
gen tenure_ceo  = year - year(becameceo)
replace tenure_ceo = . if year - year(becameceo) < 0     // data errors
gen tenure_ceo2 = tenure_ceo^2

*--- 3.5) ownership and option grants ------------------------------------------------
gen sharesowned2 = sharesowned^2

*--- 3.6) dependent variable ----------------------------------------------------------
gen ln_tdc = log(TDC1)
label variable ln_tdc "Ln(CEO total compensation, TDC1)"

* [SUBMISSION FIX] merge 1:1 aborts on duplicates, so assert uniqueness here and
* get a clear error instead of a cryptic one:
isid gvkey year


*===============================================================================
* 4) MERGE  (instruction: on gvkey and year)
*===============================================================================
merge 1:1 gvkey year using "data/execucomp_perforamance1.dta"
tab _merge                    // report these three counts in the PDF
keep if _merge == 3           // [SUBMISSION FIX] the official solution only drops _merge
drop _merge


*===============================================================================
* 5) REGRESSIONS
*===============================================================================
global CONTROLS LnAsset Volatility sharesowned sharesowned2 optionsvalue ///
                tenure_ceo tenure_ceo2

*--- Column (1): LEVEL EFFECT -- Morse et al. Table II, column (1) -----------------
reghdfe ln_tdc powerindex zROA zRstock lag_zROA lag_zRstock $CONTROLS, ///
        absorb(gvkey year) vce(robust)

outreg2 using "results/table1", excel replace ///
        ctitle(Table II column (1)) nocons dec(3) ///
        addtext(Firm FE, YES, Year FE, YES)

*--- MAX: the value of the more favourable performance measure ---------------------
* max = max(zROA, zRstock). It is CONTINUOUS, not an indicator.
* Missing propagates correctly: Stata treats missing as +infinity, so if either
* input is missing exactly one of the two replaces fires and assigns a missing.
gen max = 0
replace max = zROA    if zROA >  zRstock
replace max = zRstock if zROA <= zRstock
label variable max "max(zROA, zRstock)"

gen interaction = powerindex*max
label variable interaction "PowerIndex x Max"

*--- Column (2): RIGGING EFFECT -- Morse et al. Table III, column (3) --------------
* Same controls as column (1). N is automatically identical across the two
* columns: interaction is missing exactly when max is missing, i.e. when zROA or
* zRstock is missing -- and both are already regressors in column (1).
* [DISCUSS] There is no main effect of max in the specification, only the
* interaction, while max is a nonlinear function of zROA and zRstock, which are
* in the model. The interaction coefficient may absorb part of that level effect.
reghdfe ln_tdc powerindex interaction zROA zRstock lag_zROA lag_zRstock $CONTROLS, ///
        absorb(gvkey year) vce(robust)

outreg2 using "results/table1", excel append ///
        ctitle(Table III column (3)) nocons dec(3) ///
        addtext(Firm FE, YES, Year FE, YES)

* [DISCUSS] vce(robust), not clustered by firm. Clustering on gvkey is the usual
* choice for a firm-year panel; the official solution does not do it.
* [DISCUSS] No winsorising anywhere. ROA and Rstock have extreme values in Execucomp.

*-------------------------------------------------------------------------------
* [SUBMISSION FIX] "containing ONLY those variables and data needed to estimate
* the regressions" -- the official solution saves every column from both files.
*-------------------------------------------------------------------------------
keep gvkey year ln_tdc powerindex max interaction ///
     zROA zRstock lag_zROA lag_zRstock $CONTROLS
order gvkey year ln_tdc powerindex max interaction ///
      zROA zRstock lag_zROA lag_zRstock
compress
save "data/execucomp_morse.dta", replace
clear all


*===============================================================================
* 6) EXTENSION: firm-level climate change exposure
*    Source file: firmyear_score_2021Q4_Version_2022_Nov_22.csv from https://osf.io/fd6jq/
*===============================================================================
import delimited "data/climatechage_exposure.csv", clear

keep gvkey year cc_expo_ew
destring gvkey year cc_expo_ew, replace force   // gvkey must match the .dta type
drop if missing(gvkey, year)
duplicates drop gvkey year, force
isid gvkey year

merge 1:1 gvkey year using "data/execucomp_morse.dta"
tab _merge
keep if _merge == 3                              // [SUBMISSION FIX]
drop _merge

* Coverage note for the PDF: the OSF data start in 2002 and Execucomp ends in
* 2005, so the extension sample is effectively 2002-2005 only.
tab year

reghdfe ln_tdc cc_expo_ew powerindex interaction zROA zRstock lag_zROA lag_zRstock ///
        $CONTROLS, absorb(gvkey year) vce(robust)

outreg2 using "results/table2", excel replace ///
        ctitle(Extension Exercise) nocons dec(3) ///
        addtext(Firm FE, YES, Year FE, YES)

compress
save "data/extension_exercise.dta", replace
clear all

*===============================================================================
* End
*===============================================================================
