#!/bin/bash
set -x
python3 sweep_hour.py      > results/01_hour.log      2>&1
python3 calibrate.py       > results/02_calibrate.log 2>&1
python3 diagnose.py        > results/03_diagnose.log  2>&1
python3 sweep_control.py   > results/04_control.log   2>&1
python3 sweep_params.py    > results/05_params.log    2>&1
python3 walkforward.py     > results/06_walkfwd.log   2>&1
echo "ALL_EXPERIMENTS_COMPLETE"
