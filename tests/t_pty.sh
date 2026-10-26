#!/bin/bash
# helper for scenario S23 (called from run_tests.sh after "fresh")
( sleep 6; python3 -c "
import sys; sys.path.insert(0,'$SIMDIR')
from simlib import World
with World() as w: w['ts']['approved']=True
" ) &
HLS_REPO=$REPO python3 $SIMDIR/t_pty.py
