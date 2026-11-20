from kostral.modules.validator.engine import ValidatorEngine
from kostral.adapters.remote.server import serve


if __name__ == "__main__":
    serve(
        ValidatorEngine(),
        host="127.0.0.1",
        version="1.0.0",
        input_kinds=["Deployment","Service"],
        port=9002,
    )