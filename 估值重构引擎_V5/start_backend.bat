@echo off
cd /d "D:\长流水\估值重构引擎_V5"
start "" /MIN python -m uvicorn valuation_app.server:app --host 0.0.0.0 --port 8080
