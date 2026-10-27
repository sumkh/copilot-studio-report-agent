# Starter template for Power BI outputs (set up once)

`pbip_build.py` (Power BI reports) and `model_build.py` (the "Model check" page in semantic model packages) clone an **exemplar** report in PBIR format, so the output has your organisation's look and a report structure that Power BI Desktop has written itself. Users can supply their own sample. This starter template is used when they can't. **Without either, the agent can't build Power BI reports or semantic model packages.**

To add one:
1. In Power BI Desktop (current version), create a report connected to any published semantic model and apply your corporate theme. Add one example of each visual type you want generated with house formatting: card, table, matrix, clustered column chart, line chart, slicer.
2. **File > Save as > Power BI Project (.pbip)**.
3. Zip the `.pbip` file and the `<name>.Report` folder (the data connection is replaced at build time).
4. Put the zip in this folder, e.g. `templates/corporate_starter_pbip.zip`.
5. Set `"pbir_starter_template": "templates/corporate_starter_pbip.zip"` in `config/org-config.json` and re-package the skill.

Re-save the template with a current Power BI Desktop now and then: generated reports reuse its file-format versions.
