# SpikeSort
Spike Sorting Research.

## Environment Dependence
Follow [this](https://kilosort.readthedocs.io/en/latest/README.html) instruction to install the environment.  
```
conda
```
```
conda create --name kilosort python=3.11
conda activate kilosort
```
```
python -m pip install kilosort[gui]
```
Uninstall CPU version of PyTorch, use GPU version only: (Optional)
```
pip uninstall torch
pip3 install torch --index-url https://download.pytorch.org/whl/cu118
```
