@echo off
title Quantum AI Performance Report
echo Generating Performance Report...
python -c "import json; db=json.load(open('portfolio_db.json')); print('\n================================='); print('   PERFORMANCE REPORT'); print('================================='); print(f'Balance: ${db[\"balance\"]:.2f}'); print(f'Active Positions: {len(db[\"positions\"])}'); print(f'Closed History Trades: {len(db[\"history\"])}'); print('=================================\n')"
pause
