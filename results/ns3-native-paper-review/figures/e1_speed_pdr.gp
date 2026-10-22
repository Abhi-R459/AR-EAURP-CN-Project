set terminal svg size 1100,650 noenhanced
set output "e1_speed_pdr.svg"
set title "e1_speed — PDR"
set xlabel "Maximum speed (m/s)"
set ylabel "PDR"

set grid; set key outside right; set bmargin 14
set yrange [0:1]
plot "-"  title "A: DRL-EAURP (paper)" with yerrorlines, "-"  title "AODV (reference baseline)" with yerrorlines, "-"  title "B: DRL-EAURP (senior)" with yerrorlines, "-"  title "C: AR-EAURP (advancement)" with yerrorlines, "-"  title "EAURP (base substrate)" with yerrorlines
1 0.938667 0.057848
5 0.907 0.0868859
10 0.899667 0.0520603
15 0.909667 0.0488677
20 0.856667 0.0871063
e
1 0.945333 0.0492076
5 0.925667 0.0340669
10 0.901333 0.0559315
15 0.914667 0.0221861
20 0.891667 0.0533984
e
1 0.963 0.0356955
5 0.951 0.0417931
10 0.916333 0.0348289
15 0.912333 0.0354064
20 0.922 0.0278488
e
1 0.866 0.143201
5 0.941 0.0555853
10 0.839333 0.110978
15 0.861667 0.0689605
20 0.892333 0.047267
e
1 0.868 0.0963746
5 0.95 0.0498888
10 0.881 0.0700952
15 0.889 0.0638423
20 0.870667 0.0641244
e
