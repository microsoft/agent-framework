# Temporary scripts to test multiple models

dotenv run python test.py --assistant gpt-4.1 --user gpt-4.1
dotenv run python test.py --assistant gpt-4.1 --user gpt-4o-mini
dotenv run python test.py --assistant gpt-4o-mini --user gpt-4.1
dotenv run python test.py --assistant gpt-4.1-mini --user gpt-4.1
dotenv run python test.py --assistant gpt-4o --user gpt-4.1
dotenv run python test.py --assistant gpt-5-mini --user gpt-4.1
dotenv run python test.py --assistant gpt-5 --user gpt-4.1
