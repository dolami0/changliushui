# config/

- `endpoint_mapping.yaml` — investoday endpoint inventory. Loaded by `DataFetcher` at init.
- Original ~389-line mapping was never in git (`估值重构引擎_V5/config/` was fully gitignored) and was not found in sibling dolami0 repos; the checked-in file is a **stub** listing the paths from `docs/01_环境配置.md`. Enough for Wangqi / IndustryChainWorkflow construction.
- CLI paths used at runtime are hardcoded in `src/data_fetcher.py`; the yaml is primarily a boot/documentation token.
- Other files under this directory (if any) remain gitignored. Secrets stay in `.env` / `valuation_app/config.json` (never commit).
