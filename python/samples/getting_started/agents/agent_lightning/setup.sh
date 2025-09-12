set -ex

conda install -y numpy pandas packaging ninja ipython ipykernel wheel setuptools

pip install --no-cache-dir torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
pip install --no-cache-dir flash-attn --no-build-isolation
pip install --no-cache-dir vllm
pip install --no-cache-dir verl==0.5.0

# gcr-llm-proxy
git clone git@github.com:ultmaster/gcr-llm-proxy
pip install -r requirements.txt
dotenv run litellm --config config.yaml --host 0.0.0.0 --port 25613

# agent-lightning
git clone git@github.com:microsoft/agent-lightning
cd agent-lightning
pip install --no-cache-dir -e ".[dev,agent]"
cd ..

# agent-framework mono-repo
git clone git@github.com:ultmaster/agent-framework
cd agent-framework/python
git checkout simple-agent
pip install -e ./packages/main
pip install -e ./packages/workflow
cd ../..

# tau2-bench
git clone git@github.com:your-org/tau2-bench
cd tau2-bench
git checkout agent-sample
pip install -e .
cd ..

# test (closed source LLMs)
dotenv run python test.py --assistant gpt-4.1 --user gpt-4.1 --assistant-sliding-window 28000

# training
bash train.sh
dotenv run python lightning_client.py  # in another terminal
