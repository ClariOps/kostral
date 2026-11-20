from kostral.modules.optimizer.engine import OptimizerEngine
from kostral.adapters.remote.server import serve


if __name__ == "__main__":
    serve(
        OptimizerEngine(),
        version="1.0.0",
        input_kinds=["Deployment"],
        host="127.0.0.1",
        port=9001,
    )