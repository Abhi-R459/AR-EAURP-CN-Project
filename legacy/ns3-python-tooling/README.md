# Archived intermediate workflow

These files are the former Python launcher, aggregators, plots, report/notebook
generators and integration tests used during the first ns-3 migration stage.
They are retained as historical source, not an active or supported workflow.

The current project builds and runs native C++ through `ns3/scripts/setup.sh`
and `ns3/scripts/run.sh`. No Python launcher, analysis package or project
Python tests are required. The older Python simulation remains in
`legacy/python/`.
