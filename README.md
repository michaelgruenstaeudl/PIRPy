*PlastomeIntegrityChecks*
=========================

Scripts for evaluating plastome integrity across all available plastid genomes on NCBI

## EXAMPLE USAGE
#### On Linux / MacOS
```
# Angiosperms
TESTFOLDER=testing_angiosperms
DATE=$(date '+%Y_%m_%d')
MYQUERY='complete genome[TITLE] AND (chloroplast[TITLE] OR plastid[TITLE]) AND 2000/01/01:2019/12/31[PDAT] AND 0000050000:00000250000[SLEN] NOT unverified[TITLE] NOT partial[TITLE] AND (Embryophyta[ORGN] AND Magnoliophyta[ORGN])'
AVAILTABLE=plastome_availability_table_${DATE}.tsv
REPRTDSTAT=reported_IR_stats_table_${DATE}.tsv

# Non-angiosperm landplants
TESTFOLDER=testing_nonangiosperm_landplants
DATE=$(date '+%Y_%m_%d')
MYQUERY='complete genome[TITLE] AND (chloroplast[TITLE] OR plastid[TITLE]) AND 2000/01/01:2019/12/31[PDAT] AND 0000050000:00000250000[SLEN] NOT unverified[TITLE] NOT partial[TITLE] AND (Embryophyta[ORGN] NOT Magnoliophyta[ORGN])'
AVAILTABLE=plastome_availability_table_${DATE}.tsv
REPRTDSTAT=reported_IR_stats_table_${DATE}.tsv

mkdir -p $TESTFOLDER

# SCRIPT 01: Generating plastome availability table
python 01_generate_plastome_availability_table.py -q "$MYQUERY" -o $TESTFOLDER/$AVAILTABLE 1>>$TESTFOLDER/Script01_${DATE}.runlog 2>&1

# SCRIPT 02: Downloading records and extracting IR information
mkdir -p $TESTFOLDER/records_${DATE}
mkdir -p $TESTFOLDER/data_${DATE}
python 02_download_records_and_extract_IRs.py -i $TESTFOLDER/$AVAILTABLE -r $TESTFOLDER/records_${DATE}/ -d $TESTFOLDER/data_${DATE}/ -o $TESTFOLDER/$REPRTDSTAT 1>>$TESTFOLDER/Script02_${DATE}.runlog 2>&1

# SCRIPT 03: Comparing the reported IR information
#python3 ../PlastomeIntegrityChecks/02_download_records_and_extract_aspects.py -l $(awk 'NR > 1 {print $2}' summaries.tsv) -o .

# SCRIPT 04: Comparing the IRs to generate accurate IR information
#python3 ../PlastomeIntegrityChecks/03_compare_existing_IRs.py -o align_info.csv -i NC_*.tar.gz

```

#### HELPFUL
Self-blasting of the plastid genome sequence in order to infer the IR length
```
INF=chloroplastGenome.gb
python gb2fas.py $INF
blastn -subject ${INF%.gb*}.fas -query ${INF%.gb*}.fas -outfmt 7 -strand 'both' |\
 awk '{ if ($4 > 10000 && $4 < 50000) print $4, $7, $8, $9, $10}' >  ${INF%.gb*}_IRs.txt
```

<!--
## FULL USAGE
```
#python3 ../PlastomeIntegrityChecks/01_generate_plastome_availability_table.py -o summaries.csv -q "Magnoliophyta[ORGN] AND 00000180000[SLEN] : 00000200000[SLEN] AND complete genome[TITLE] AND (chloroplast[TITLE] OR plastid[TITLE])"
```
-->

## VISUALIZATIONS, GRAPHS & STATISTICAL TESTS
#### TO DO
* Please plot the growth in plastid genomes (as done via visulations script 01), but not with the number of plastid genomes on the y-axis but with the number of unique genera plotted. (This will illustrate if the current growth in plastid genome number is reflective of a better taxonomic survey or of higher sampling in genera and families.)

* Please conduct statistical test to see if the absence of reported IRs (i.e., "no" in column "IRa_REPORTED") higher for an unpublished status (i.e., "Unpublished" in column "TITLE") and a published status (i.e., any other value in column "TITLE")?

* Please conduct statistical test to see if the absence of reported IRs (i.e., "no" in column "IRa_REPORTED") higher for records with a version number of 1 as compared to higher version numbers (see column "VERSION")?

* Please plot the distribution by how many nucleotides the individual records have misidentified the IR length. (It would be interesting to see if the mis-estimation is normally distributed or if there is a skew in the distribution.)
