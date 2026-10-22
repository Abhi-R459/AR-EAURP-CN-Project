set terminal svg size 1100,650 noenhanced
set output "e6_overhead_pdr.svg"
set title "e6_overhead — PDR"
set xlabel "Configuration"
set ylabel "PDR"

set grid; set key outside right; set bmargin 14
set yrange [0:1]
set xtics rotate by -45 ('AODV (reference baseline)' 1,'EAURP (base substrate)' 2,'A: DRL-EAURP (paper)' 3,'B: DRL-EAURP (senior)' 4,'C: AR-EAURP (advancement)' 5,'C without ECC' 6)
plot "-"  title "pdr" with yerrorlines
1 0.836667 0.0962202
2 0.826667 0.0284312
3 0.826 0.106534
4 0.864 0.0684815
5 0.839 0.080774
6 0.840333 0.0451448
e
