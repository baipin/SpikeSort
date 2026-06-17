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

Install Jupter in this environment:
```
conda install jupyter
```
## Execution
To run kilosort, use this code:
```
conda activate kilosort
```
Open jupyter lab to start work:`jupyter lab`. Or open GUI with `python -m kilosort`.

## Environment Dependence from week 6

From week 6 (6.ipynb), you need to install more environment dependence. Follow [Installation of IBL Unified Environment](https://docs.internationalbrainlab.org/02_installation.html) to install the environment.   
Run them line by line:   
```
conda update -n base -c defaults conda
conda create --name ibl python=3.13 --yes
conda activate ibl

pip install ONE-api
pip install ibllib
```
Register the environment (ibl) to Jupyter:
```
pip install ipykernel
python -m ipykernel install --user --name iblenv --display-name "Python (ibl)"
```
Also, register kilosort environment to jupyter:
```
conda activate kilosort
python -m ipykernel install --user --name kilosort --display-name "Python (Kilosort)"
```
After this, you can switch to any kernel in any environment. Just run `jupyter lab F:\`in any environment including base is okay.

