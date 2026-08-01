# SpikeSort
Spike Sorting Research.

## Environment Dependence (Week 1- 5)
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

## Environment Dependence (Week 6-9)

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

## Environment Dependence (from Week10)

Please see the readme file under `/esp32s3-banwidth-sender` folder.

## Architecture

Large generated data is kept out of the repository root:

- `data/preprocessed/`: large preprocessed arrays such as `whitened_data.npy`.
- `data/reconstructed/`: reconstructed `.bin` streams and paired quantization metadata.
- `data/dct_coefficients/`: large DCT coefficient rebuild caches.
- `data/week4_fixed_template/`: large Week 4 fixed-template control binaries.
- `outputs/caches/`: reusable evaluation caches such as baseline and compression results.
- `outputs/week4/`, `outputs/week5/`, `outputs/week7/`, `outputs/week8/`: week-specific result tables and caches.
- `reports/`: generated reports, PDFs, LaTeX outputs, and presentation artifacts.

Some data filed are excluded. You can obtain these files by executing the notebook code on your own device after clone this repository.

## Notebook Overview

- `1.ipynb`: Downloads the short Neuropixels sample dataset, prepares Kilosort probe files, and runs the initial baseline Kilosort workflow used by later notebooks.
- `2.ipynb`: Continues the baseline workflow, applies DCT compression experiments to preprocessed neural signals, rebuilds `whitened_data.npy`, and generates compression evaluation caches.
- `3.ipynb`: Evaluates compressed-data sorting against the baseline using baseline-anchored spike labeling, nearest/mutual/Hungarian-style time matching, and detection-time metrics.
- `4.ipynb`: Runs strict fixed-baseline-template sorting on compressed reconstructed data and evaluates binned spike-count accuracy across compression ratios.
- `5.ipynb`: Studies neuron-level sensitivity under different compression ratios, builds per-neuron accuracy tables, and trains/uses the accuracy predictor and ratio recommender.
- `6.ipynb`: Introduces the IBL/ONE workflow with behavioral trial loading and basic behavioral performance examples.
- `7.ipynb`: Redraws constraint-aware keep-ratio diagnostics from cached Week 5 results, comparing mean-bin and all-neuron accuracy constraints.
- `8.ipynb`: Works with OpenAlyx raw electrophysiology sessions, downloads/decompresses AP data when needed, runs Kilosort4 on full or partial data, and evaluates DCT-compressed partial runs.
- `9.ipynb`: Discovers Week 8 partial DCT Kilosort outputs, applies the learned predictor, and generates compression-ratio recommendations for each recording.
-  `/esp32s3-banwidth-sender`: Esp32 hardware research.