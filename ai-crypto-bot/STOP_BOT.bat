@echo off
title Quantum AI Paper Bot - Stopping
echo Stopping Quantum AI Paper Bot processes...
taskkill /FI "WINDOWTITLE eq Quantum AI Paper Bot - Running*" /F
echo Bot stopped safely.
pause
