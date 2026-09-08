#!/bin/bash
python3 robust.py        > results/07_robust.log  2>&1
python3 walkforward.py   > results/06_walkfwd.log 2>&1
python3 sweep_v2_main.py > results/08_v2.log      2>&1
echo REST_COMPLETE
