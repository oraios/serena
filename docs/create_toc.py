import os
from pathlib import Path

# This script provides a platform-independent way of making the jupyter-book call (used in pyproject.toml)
folder = Path(__file__).parent
toc_file = folder / "_toc.yml"
cmd = f"jupyter-book toc from-project docs -e .rst -e .md -e .ipynb >{toc_file}"
print(cmd)
os.system(cmd)
