import json
import os
import sys
from functools import partial
from pathlib import Path
from typing import Callable, Mapping, Sequence

__all__ = ["node_modules"]

node_modules = Path(__file__).parent / "node_modules"


def run_script(module: str, script: str, args: Sequence[str]) -> None:
    """
    Run a script from a node module. Used as an entrypoint for Python package
    managers in order to convert Node bins into Python bins.

    Parameters
    ----------
    module
        Name of the Node module
    script
        Name of the script to run (relative to the Node module's dir)
    args
        Arguments to pass to the script (excluding the script name)
    """

    os.execvp("node", ["node", str(node_modules / module / script), *args])


class EntryPoints:
    """
    Generates all the entrypoint functions for a given package.
    """

    def __init__(self, package: str, scripts: Mapping[str, str]) -> None:
        self.package = package
        self.scripts = scripts

    @classmethod
    def from_json(cls, spec: str) -> "EntryPoints":
        """
        Create an entrypoint generator from a JSON string. This exists to ease
        code generation.

        Parameters
        ----------
        spec
            JSON string containing the package name and the mapping of script
            names to script paths.

        Returns
        -------
        EntryPoints
            Entry point generator
        """

        data = json.loads(spec)
        return cls(data["package"], data["scripts"])

    def __getattr__(self, item: str) -> Callable[[Sequence[str]], None]:
        """
        Get an entrypoint function for a given script.

        Parameters
        ----------
        item
            Name of the script
        """

        if item in self.scripts:
            return partial(run_script, self.package, self.scripts[item], sys.argv[1:])
        else:
            raise AttributeError(
                "Script {} not found in package {}".format(item, self.package)
            )
