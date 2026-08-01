# Academic Visualization Portal

This folder is a static site wrapper for two existing pages:

- `ibl-viz/`: IBL Viz ss_2024-05-06 dataset directory.
- `esp32-reports/`: ESP32-S3 bandwidth report browser.

Deploy the whole `integrated-static-site` folder to Vercel as a static project. The root `index.html` lets users choose which page to open.

## Local Preview

For the IBL page, use a local static server because it loads CSV files with `fetch()`:

```powershell
cd integrated-static-site
python -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

The ESP32 report page can also be opened through the same local server.
