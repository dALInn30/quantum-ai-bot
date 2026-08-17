@echo off
title Quantum AI 90-Day Backtest Simulator
echo Running 90-Day Backtest Simulation on Quantfury coins...
python -c "import server; res = server.run_backtest_simulation(); print('\n================================='); print('   90-DAY BACKTEST RESULTS'); print('================================='); print(f'Total Trades: {res[\"total_trades\"]}'); print(f'Win Rate: {res[\"win_rate\"]}%'); print(f'Simulated Net PnL: ${res[\"total_pnl\"]:.2f}'); print(f'Best Performing Coin: {res[\"best_symbol\"]}'); print('=================================\n')"
pause
