# Contributing

Kostral is early and its engine contract is a draft, so the most useful contributions right now are feedback and bug reports.

## Most useful now

1. **Run it on your own manifests** and open an issue with the manifest (or a trimmed copy) and the output, especially if a finding is wrong, missing or unclear.
2. **Read the [engine contract](docs/engine-contract.md)** and comment on what is missing, unclear or too strict. This matters most if you maintain a tool you would want to run as an engine.
3. **Report bugs**, with the command you ran, the exit code and what you expected.

## Development setup

```bash
pip install -e .
python -m unittest discover -s tests -t . -v
python tests/report.py        # regenerates docs/transparency/test-report.md
```

See [tests/README.md](tests/README.md) for what the tests cover and how snapshots work.

## Rules for changes

- A doc may only describe something that has a test or an example behind it.
- A change to a guarantee needs a test, and [docs/guarantees.md](docs/guarantees.md) must name it.
- Keep the workflow explicit and readable: the order of engines belongs in the workflow, not inside engines.
- Old documents live in [docs/archive](docs/archive/README.md) and are not maintained.
