@echo off
pip install -r requirements.txt
python -m playwright install chromium
python demo\make_demo.py
python scripts\run_qa.py --all
pause
