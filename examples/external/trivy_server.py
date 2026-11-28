"""Serve Trivy as a remote external engine on port 9012.

NOT verified against a real Trivy in this repository's tests: the command below is a
starting point. Pin YOUR Trivy version, run the command once by hand on a folder of
YAML files, and keep the SARIF it prints as a fixture before trusting the mapping.
Do not add --exit-code: a non-zero exit is how KOSTRAL recognises a broken tool.

    export KOSTRAL_TOKEN_TRIVY=<at least 16 characters>
    python examples/external/trivy_server.py
"""
from kostral.adapters.external.server import serve

if __name__ == "__main__":
    serve("trivy", version="0.76.2", input_kinds=["*"],
          command=["trivy", "config", "--format", "sarif", "--quiet", "{dir}"],
          token_env="KOSTRAL_TOKEN_TRIVY", host="127.0.0.1", port=9012, timeout=120)