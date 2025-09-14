set -x
dotenv run python test.py --assistant Qwen2.5-1.5B-Instruct --user gpt-4.1 --assistant-sliding-window 4000
dotenv run python test.py --assistant gpt-4.1 --user gpt-4.1 --assistant-sliding-window 4000
dotenv run python test.py --assistant gpt-4.1 --user gpt-4.1 --assistant-sliding-window 28000
dotenv run python test.py --assistant gpt-4.1 --user gpt-4o-mini --assistant-sliding-window 28000
dotenv run python test.py --assistant gpt-4o-mini --user gpt-4.1 --assistant-sliding-window 28000
dotenv run python test.py --assistant gpt-4.1-mini --user gpt-4.1 --assistant-sliding-window 28000
dotenv run python test.py --assistant gpt-5-mini --user gpt-4.1 --assistant-sliding-window 28000
dotenv run python test.py --assistant gpt-5 --user gpt-4.1 --assistant-sliding-window 28000
