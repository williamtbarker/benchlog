# macOS setup

BenchLog supports Python 3.10 or newer and has no runtime dependencies.

```bash
cd ~/Documents/GPT_Hist_Review/benchlog
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
./scripts/verify.sh
```

If `python3 --version` is older than 3.10, install a current Python with
`brew install python`. The verification script needs Git and standard macOS command-line tools;
install them with `xcode-select --install` if necessary.

For later sessions:

```bash
cd ~/Documents/GPT_Hist_Review/benchlog
source .venv/bin/activate
benchlog --help
```
