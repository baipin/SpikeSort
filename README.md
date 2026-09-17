# ACADEMIC Research Workspace

This repository contains two related research tracks:

- Spike-sorting and neural-data compression experiments, developed through the
  numbered notebooks and the supporting `data/`, `outputs/`, and `reports/`
  directories.
- ESP32-S3 wireless bandwidth experiments, including firmware, receiver-side
  capture tooling, field-terminal controls, offline analysis, and the static
  report portal under `esp32s3-bandwidth-sender/` and
  `integrated-static-site/`.

## Repository Map

| Path | Purpose | Version-control policy |
| --- | --- | --- |
| `1.ipynb` ... `9.ipynb` | Notebook-based spike-sorting workflow | Tracked source notebooks |
| `data/`, `ONE/`, `kilosort4/`, `week8_*`, `week9_*` | Large raw data and local Kilosort outputs | Ignored local artifacts |
| `esp32s3-bandwidth-sender/main/` | ESP32-S3 firmware | Tracked source |
| `esp32s3-bandwidth-sender/receiver.py` and `udp_receiver.py` | Receiver and capture pipeline | Tracked source |
| `esp32s3-bandwidth-sender/field_terminal/` | LAN operator terminal and metadata workflow | Tracked source and documentation |
| `esp32s3-bandwidth-sender/tools/` | Flashing, capture, analysis, and report builders | Tracked source |
| `esp32s3-bandwidth-sender/captures/` | Raw field captures | Local, ignored data; do not delete during source cleanup |
| `esp32s3-bandwidth-sender/reports/` | Reproducible summaries and selected report artifacts | Curated outputs; LaTeX intermediates are ignored |
| `integrated-static-site/` | Static browser for IBL and ESP32 reports | Deployable site |

## ESP32 Field Reports

The current battery-position report covers the three directories under
`esp32s3-bandwidth-sender/captures/udp_battery_position_series_20260901/new/`:
`new_chair`, `new_control`, and `new_rec`. The report includes 50 ms
ESP32-send-timestamp-aligned throughput, empty-window rate, within-run window
variance, run-to-run variance, standard deviation, coefficient of variation,
and descriptive 95% confidence intervals.

Two operator-reviewed interrupted runs are marked
`DISCONNECTED/EXCLUDED` in the report. Both all-run and cleaned statistics are
retained. The generated report source, PDF, index CSV, figures, and offline
replay outputs are in:

```text
esp32s3-bandwidth-sender/reports/udp_battery_position_series_20260901/new/
```

To regenerate the report from the captures:

```powershell
cd G:\ACADEMIC\esp32s3-bandwidth-sender
python tools\build_battery_position_series_report.py `
  --capture-root captures\udp_battery_position_series_20260901\new `
  --report-root reports\udp_battery_position_series_20260901\new `
  --include-groups new_chair,new_control,new_rec `
  --report-date 2026-09-10 `
  --report-basename new_battery_position_series_report
```

The LAN field terminal is started from the ESP32 project root with:

```powershell
python field_terminal\server.py
```

The terminal stores raw captures and metadata only. Image generation, report
writing, and offline analysis are explicit post-processing steps.

## Local Hygiene

Python caches, notebook checkpoints, ESP-IDF builds, TeX caches, QA renders,
temporary logs, and generated document intermediates are ignored and may be
removed safely. Raw captures and curated report outputs are kept separate from
these caches. Before committing, use:

```powershell
git status
git diff --check
```

## Spike-Sorting Workflow

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

Data and output folders:

```text
data/
|-- preprocessed/          # Large preprocessed arrays, e.g. whitened_data.npy
|-- reconstructed/         # Reconstructed binary streams and quantization metadata
|-- dct_coefficients/      # Large DCT coefficient rebuild caches
`-- week4_fixed_template/  # Large Week 4 fixed-template control binaries

outputs/
|-- caches/                # Reusable baseline/compression evaluation caches
|-- week4/                 # Week 4 fixed-template sorting summaries and ratio tables
|-- week5/                 # Week 5 neuron sensitivity tables and figures
|-- week7/                 # Constraint-aware keep-ratio diagnostic outputs
`-- week8/                 # Week 8 manifests and small exported metadata

reports/
|-- week4/                 # Week 4 generated report files
`-- week45/                # Week 4/5 presentation and LaTeX artifacts

esp32s3-bandwidth-sender/  # ESP32-S3 bandwidth monitor firmware, receiver, dashboard, and reports
```

Large raw data, reconstructed binaries, Kilosort run directories, ESP32 build artifacts, and receiver captures are local artifacts and are intentionally ignored by Git.

Some data files are excluded. You can obtain these files by executing the notebook code on your own device after clone this repository.
