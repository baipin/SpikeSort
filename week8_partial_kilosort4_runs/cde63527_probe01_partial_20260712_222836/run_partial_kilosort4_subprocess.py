
from pathlib import Path
import json
import sys

from kilosort import run_kilosort

run_info_path = Path(sys.argv[1])
settings_path = Path(sys.argv[2])
results_dir = Path(sys.argv[3])
save_extra_vars = False
clear_cache = True

run_info = json.loads(run_info_path.read_text(encoding='utf-8'))
settings_raw = json.loads(settings_path.read_text(encoding='utf-8'))
settings = dict(settings_raw)
settings['filename'] = Path(settings['filename'])

results_dir.mkdir(parents=True, exist_ok=True)
run_kilosort(
    settings=settings,
    probe_name='NeuroPix1_default.mat',
    results_dir=results_dir,
    data_dtype='int16',
    save_extra_vars=save_extra_vars,
    clear_cache=clear_cache,
    verbose_console=True,
)
run_info['partial_kilosort_results_dir'] = str(results_dir)
run_info['partial_kilosort_settings'] = {k: str(v) for k, v in settings.items()}
run_info['partial_kilosort_status'] = 'complete'
(run_info_path.parent / 'run_info_partial_kilosort4.json').write_text(json.dumps(run_info, indent=2), encoding='utf-8')
