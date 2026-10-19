#!/bin/zsh
# Wide search, round A: fine-tune from the four best bases with the 17-gene
# genome (reward shaping, PPO optimisation, data collection), 1-4 genes
# changed per child by up to 3x each, 32 children per generation, 8
# generations, 8M steps per child. Every child is a standard-tested MLflow
# run in experiment evolve-wideA.
set -e
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
source scripts/campaigns/mlflow_env.sh
uv run python scripts/evolve.py \
  --base runs/evolve/full1013/gen_10/g10m20/model.pt runs/F3_scratch200M_s23/best.pt \
         runs/evolve/evo10/gen_10/g10m08/model.pt runs/evolve/full1012/gen_09/g9m03/model.pt \
  --timeout-penalty 4 --name wideA --generations 8 --population 32 --survivors 10 --steps 8000000 --workers 8
echo "wide A done: $(date)"
