*********************************************************************************************
***FIDM 2023-2024 
***Replication Task Solution
*** Input: 1) "execucomp_executive.dta"
***        2) "execucomp_perforamance.dta"
***        3) "climatechage_exposure.csv"
*** Output: 1) regression output
*********************************************************************************************

clear all 
*** 0) Change directory
cd "C:\Users\cui\Dropbox\2023-2024\topic 5 - Stata workshop material\Replication_Assignment 2023"
*** cd "here you need to write the path to your file"

*** 1) import company financial information 
use "data\execucomp_perforamance.dta", clear 

*** 2) generate variables for company financial information 
*** 2.1) rename variables 
rename GVKEY gvkey
rename ASSETS assets
rename PRCCF prccf
rename YEAR year
rename BS_VOLATILITY bs_volatility
rename SIC sic
rename AJEX ajex

*** 2.2) set to panel data mode 
duplicates list gvkey year
destring gvkey, replace 
xtset gvkey year

*** 2.3) generate or rename company controls
gen LnAsset = log(assets)
rename bs_volatility Volatility
gen Rstock = (prccf/ajex)/(l.prccf/l.ajex) - 1
tostring sic, replace 
replace sic = "0" + sic if strlen(sic) == 3
gen sic2 = substr(sic,1,2)
sort sic2 year  
by sic2 year: egen mean_sic2_year_ROA = mean(ROA)
by sic2 year: egen std_sic2_year_ROA = sd(ROA)
by sic2 year: egen mean_sic2_year_Rstock = mean(Rstock)
by sic2 year: egen std_sic2_year_Rstock = sd(Rstock)

gen zROA = (ROA - mean_sic2_year_ROA) / std_sic2_year_ROA
gen zRstock = (Rstock - mean_sic2_year_Rstock) / std_sic2_year_Rstock

xtset gvkey year
gen lag_zROA = l.zROA
gen lag_zRstock = l.zRstock

save "data\execucomp_perforamance1.dta", replace
clear all


*** 3) generate variables for executive information  
use "data\execucomp_executive.dta", clear

*** 3.1) powerindex
gen lower_title = lower(TITLE)
gen powerindex = 0
replace powerindex = 1 if strpos(lower_title,"chairman") > 0 | strpos(lower_title,"chairwoman") > 0 | strpos(lower_title,"chairperson") > 0 // **

replace powerindex = 2 if (strpos(lower_title,"chairman") > 0 | strpos(lower_title,"chairwoman") > 0 | strpos(lower_title,"chairperson") > 0) & strpos(lower_title,"president") > 0 // **

*** 3.2) executive controls 
rename CEOANN ceoann
rename YEAR year
rename SHROWN_EXCL_OPTS_PCT shrown_excl_opts_pct
rename BECAMECEO becameceo
sum 
rename OPTION_AWARDS_BLK_VALUE option_awards_blk_value
rename shrown_excl_opts_pct sharesowned
rename GVKEY gvkey 
destring gvkey, replace 

*** 3.3) keep only CEO
gen CEO = 0
replace CEO = 1 if ceoann == "CEO"
keep if CEO == 1

*** 3.4) generate CEO tenure 
gen tenure_ceo = year - year(becameceo) 
replace tenure_ceo = . if year - year(becameceo) < 0
gen tenure_ceo2 = tenure_ceo^2

*** 3.5) sharesowned and optionvalue
// sum sharesowned,d
gen sharesowned2 = sharesowned^2
rename option_awards_blk_value optionsvalue

*** 3.6) Ln total compensation
gen ln_tdc = log(TDC1)

*** 4) link company_financials frame with executives_information frame 
merge 1:1 gvkey year using "data\execucomp_perforamance1.dta"
drop _merge

*** 5) Regression analysis
*** Table II column (1)
reghdfe ln_tdc powerindex zROA zRstock lag_zROA lag_zRstock LnAsset Volatility sharesowned sharesowned2 optionsvalue tenure_ceo tenure_ceo2,absorb(gvkey year) vce(robust)
outreg2 using "results\table1", excel replace ctitle(Table II column (1)) nocons dec(3) addtext(Firm FE, YES,  Year FE, YES)

*** Table III column (3)
gen max = 0
replace max = zROA if zROA > zRstock
replace max = zRstock if zROA <= zRstock

gen interaction = powerindex*max

reghdfe ln_tdc powerindex interaction zROA zRstock lag_zROA lag_zRstock LnAsset Volatility sharesowned sharesowned2 optionsvalue tenure_ceo tenure_ceo2,absorb(gvkey year) vce(robust)
outreg2 using "results\table1", excel append ctitle(Table III column (3)) nocons dec(3) addtext(Firm FE, YES,  Year FE, YES)

save "data\execucomp_morse.dta", replace
clear all

***6) Extension
import delimited "data\climatechage_exposure.csv"
keep gvkey year cc_expo_ew
duplicates drop gvkey year, force

merge 1:1 gvkey year using "data\execucomp_morse.dta"

reghdfe ln_tdc cc_expo_ew powerindex interaction zROA zRstock lag_zROA lag_zRstock LnAsset Volatility sharesowned sharesowned2 optionsvalue tenure_ceo tenure_ceo2,absorb(gvkey year) vce(robust)
outreg2 using "results\table2", excel replace ctitle(Extension Exercise) nocons dec(3) addtext(Firm FE, YES,  Year FE, YES)

save "data\extension_exercise.dta", replace
clear all



*** End



