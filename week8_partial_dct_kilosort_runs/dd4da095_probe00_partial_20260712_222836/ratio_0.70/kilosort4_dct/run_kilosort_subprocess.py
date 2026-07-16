
from pathlib import Path
import json
import sys
from kilosort import run_kilosort

settings_path = Path(sys.argv[1])
results_dir = Path(sys.argv[2])
settings_raw = json.loads(settings_path.read_text(encoding='utf-8'))

# Keep subprocess-control flags out of the Kilosort settings dict; Kilosort
# validates settings keys and rejects unknown names such as _do_CAR.
do_CAR = bool(settings_raw.pop('_do_CAR', True))
save_extra_vars = bool(settings_raw.pop('_save_extra_vars', False))
clear_cache = bool(settings_raw.pop('_clear_cache', True))
save_preprocessed_copy = bool(settings_raw.pop('_save_preprocessed_copy', False))
filename = Path(settings_raw.pop('filename'))

run_kilosort(
    settings=settings_raw,
    filename=filename,
    probe_name='NeuroPix1_default.mat',
    results_dir=results_dir,
    data_dtype='int16',
    do_CAR=do_CAR,
    save_extra_vars=save_extra_vars,
    clear_cache=clear_cache,
    save_preprocessed_copy=save_preprocessed_copy,
    verbose_console=True,
)
