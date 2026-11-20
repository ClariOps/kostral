from kostral.modules.security.engine import SecurityEngine
from kostral.adapters.remote.server import serve


if __name__ == "__main__":
    serve(
        SecurityEngine(),
        version="1.0.0",
        input_kinds=["Deployment"],
        host="127.0.0.1",
        port=9003,
    )