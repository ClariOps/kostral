import os, argparse
from kostral.core.ir import (DeploymentIR, ServiceIR, HelmIR, IngressIR, ConfigMapIR, SecretIR, PVCIR, OpaqueIR)
import importlib.util
from colorama import Fore, Style, init
from kostral.modules.coverage.engine import CoverageEngine
IR_MAPPING = {
    "Deployment": DeploymentIR,
    "Service": ServiceIR,
    "Ingress": IngressIR,
    "ConfigMap": ConfigMapIR,
    "Secret": SecretIR,
    "PersistentVolumeClaim": PVCIR,
}

def load_workflow(path):

    spec = importlib.util.spec_from_file_location(
        "kostral_user_workflow",
        path,
    )

    if spec is None or spec.loader is None:
        raise ValueError(
            f"Unable to load workflow: {path}"
        )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


def _to_ir(data):
    """Mechanical mapping only: typed IR if known, OpaqueIR otherwise."""
    ir_class = IR_MAPPING.get(data.get("kind"), OpaqueIR)
    return ir_class(manifest=data)


def load_yaml_irs(user_path, logger):
    import glob, os, yaml, sys

    irs = []

    def collect(documents):
        for data in documents:
            if not data or not isinstance(data, dict) or "kind" not in data:
                continue
            irs.append(_to_ir(data))

    if user_path == "-":
        collect(yaml.safe_load_all(sys.stdin.read()))
        return irs

    if os.path.isdir(user_path):
        search_pattern = os.path.join(user_path, "*.y*ml")
    else:
        search_pattern = user_path

    for filepath in sorted(glob.glob(search_pattern)):
        with open(filepath, "r") as f:
            collect(yaml.safe_load_all(f))

    return irs

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_CRASH = 3

def exit_code_for(ctx):
    """Determine process exit code from the completed RunContext."""

    if ctx.report.has_errors():
        return EXIT_FINDINGS

    if ctx.artifacts.get("deploy_error"):
        return EXIT_FINDINGS

    return EXIT_OK


def build_opts(args):
    opts = {}

    if args.target:
        opts["target"] = args.target

    if getattr(args, "context", None):
        opts["context"] = args.context

    if args.dry_run:
        opts["dry_run"] = True

    if args.skip_rules:
        opts["skip_rules"] = args.skip_rules

    if args.allow_rules:
        opts["allow_rules"] = args.allow_rules

    if getattr(args, "apply_aks_defaults", None):
        opts["apply_aks_defaults"] = True

    return opts


def render_banner():
    banner = r"""
██╗  ██╗ ██████╗ ███████╗████████╗██████╗  █████╗ ██╗     
██║ ██╔╝██╔═══██╗██╔════╝╚══██╔══╝██╔══██╗██╔══██╗██║     
█████╔╝ ██║   ██║███████╗   ██║   ██████╔╝███████║██║     
██╔═██╗ ██║   ██║╚════██║   ██║   ██╔══██╗██╔══██║██║     
██║  ██╗╚██████╔╝███████║   ██║   ██║  ██║██║  ██║███████╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝

Kostral — Pre-Deployment Intelligence System
────────────────────────────────────────────
Analyze • Optimize • Validate • Secure

"Making Kubernetes predictable before it runs"
"""
    init(autoreset=True)
    print(Fore.GREEN + banner + Style.RESET_ALL)


def valid_file(path):
    if path == "-":
        return path

    if not os.path.exists(path):
        raise argparse.ArgumentTypeError(
            f"File not found: {path}"
        )

    return path

class KostralRunner:

    def __init__(self, workflow):
        self.workflow = workflow

    def run(self, ctx):
        # Mandatory KOSTRAL system responsibility
        CoverageEngine().process(ctx)

        # User-composed workflow
        return self.workflow.run(ctx)