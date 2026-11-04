import logging
from kostral.core.base import Module
from kostral.core.context import RunContext

from kostral.modules.validator.rules.replicaScalingRule import ReplicaScalingSuggestionRule
from kostral.modules.validator.rules.overProvisioningRule import OverProvisioningRule
from kostral.modules.validator.rules.underProvisioningRule import UnderProvisioningRule
from kostral.modules.validator.rules.noReadinessProbe import ReadinessProbeMissingRule
from kostral.modules.validator.rules.noLivenessProbe import NoLivenessProbeRule
from kostral.modules.validator.rules.nodePortWarning import NodePortExposureRule


logger = logging.getLogger(__name__)


class ValidatorEngine(Module):
    name = "validator-engine"
    #logger.info("Initializing Validator ... ")

    def __init__(self):
        self.rules = [
            ReplicaScalingSuggestionRule(), 
            OverProvisioningRule(),
            UnderProvisioningRule(),
            ReadinessProbeMissingRule(),
            NoLivenessProbeRule(),
            NodePortExposureRule()
        ]

    def process(self, ctx: RunContext) -> None:
        logger.info(f"Initializing Validator ...")
        
        for rule in self.rules:
            if not rule.enabled(ctx):
                continue
            
            for ir in ctx.irs:    
                rule.execute(ir, ctx)

        logger.info(f"Validator completed\n")