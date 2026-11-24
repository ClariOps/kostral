from typing import Dict, List, Optional,Any
from kostral.core.base import IR
from copy import deepcopy

class ConfigMapIR(IR):
    kind = "ConfigMapIR"

    def __init__(
        self,
        *,
        name: str = None,
        data: dict = None,
        manifest: dict = None,
    ):
        if manifest:
            self._from_manifest(manifest)
        else:        
            self.name = name
            self.data = data                  # key-value pairs
    
        
    def __repr__(self):
        return f"ConfigMapIR(name={self.name}, keys={list(self.data.keys())})"

    def _from_manifest(self, m: dict):
        self._source = deepcopy(m)

        self.name = m["metadata"]["name"]
        self.data = m.get("data")

        self._loaded = deepcopy({
            "name": self.name,
            "data": self.data,
        })
        
    def to_manifest(self) -> dict:
        if (getattr(self, "_source", None) is not None 
            and {"name": self.name, "data": self.data} == self._loaded
        ):
            return deepcopy(self._source)
