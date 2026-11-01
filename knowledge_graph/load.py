"""Run one loader or all of them: .venv/bin/python knowledge_graph/load.py <slug> [...]

Each loaders/<slug>.py has a main(). Reruns skip parts already stored.
"""
import importlib.util
import sys
import traceback

import kg


def run(name):
    spec = importlib.util.spec_from_file_location("loader_" + name, kg.HERE / "loaders" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.stem for p in (kg.HERE / "loaders").glob("[!_]*.py"))
    failed = []
    for name in names:
        try:
            run(name)
        except Exception:
            traceback.print_exc()
            failed.append(name)
    if failed:
        sys.exit("failed: " + ", ".join(failed))
