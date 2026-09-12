"""What must agree across the tree. Run it like ruff: uv run python invariants.py

Not tests. Each check states one agreement between two declarations that drift
apart silently -- the registry and the code, the imports and the dependencies,
a copy and the copy it was made from. One statement each, for every image.
"""

import ast
import os
import re
import sys
import tomllib

ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGES = ("backend", "metrics", "layout", "vlm", "datasets", "fleet")
ALIAS = {"opencv-python-headless": "cv2", "pyyaml": "yaml", "argon2-cffi": "argon2",
         "docling-slim": "docling", "docling-core": "docling_core"}
# Knobs read by something other than our Python, with the reader named.
READ_ELSEWHERE = {"vlm": {"VLLM_USE_FLASHINFER_SAMPLER"}}  # vLLM, from the environment we hand the child
# A dependency no import of ours names, because something else reaches for it:
# fastapi wants the form parser, docling wants the spatial index.
RUNTIME_ONLY = {"backend": {"python-multipart"}, "metrics": set(),
                "layout": {"rtree"}, "vlm": set(), "fleet": set(), "datasets": set()}


def pkg(image):
    return os.path.join(ROOT, "images", image, image)


def sources(image, tests=False):
    roots = [pkg(image)] + ([os.path.join(ROOT, "images", image, "tests")] if tests else [])
    for r in roots:
        for dp, _, fs in os.walk(r):
            if "__pycache__" in dp:
                continue
            for f in fs:
                if f.endswith(".py"):
                    yield os.path.join(dp, f)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def imports(image, tests=False):
    out = set()
    for p in sources(image, tests):
        for node in ast.walk(ast.parse(read(p))):
            if isinstance(node, ast.Import):
                out |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                out.add(node.module.split(".")[0])
    return out


def knobs_read(image):
    got = set()
    for p in sources(image):
        got |= set(re.findall(r"""knobs\.(?:knob|number)\(['"]([A-Z_0-9]+)['"]""", read(p)))
    return got


def declared_knobs(image):
    src = read(os.path.join(pkg(image), "knobs.py")) if os.path.exists(os.path.join(pkg(image), "knobs.py")) else ""
    return {m[0]: bool(m[1]) for m in re.findall(r'Knob\(\s*"([A-Z_0-9]+)",(?:[^)]*?debt=(True))?[^)]*?\)', src, re.S)}


def project(image):
    with open(os.path.join(ROOT, "images", image, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)


# ---- the agreements ----

def no_image_reaches_another(fail):
    for i in IMAGES:
        for bad in sorted(imports(i, tests=True) & (set(IMAGES) - {i})):
            fail(f"{i} imports {bad}: an image is self-contained")


def the_registry_and_the_code_agree(fail):
    for i in IMAGES:
        declared = declared_knobs(i)
        if not declared and not os.path.exists(os.path.join(pkg(i), "knobs.py")):
            continue
        for n in sorted(knobs_read(i) - set(declared)):
            fail(f"{i}: reads {n} past the registry; declare it in knobs.py")
        idle = set(declared) - knobs_read(i) - READ_ELSEWHERE.get(i, set())
        for n in sorted(n for n in idle if not declared[n]):
            fail(f"{i}: declares {n} and reads it nowhere; read it, drop it, or mark it debt=True")


def the_dependencies_and_the_imports_agree(fail):
    for i in IMAGES:
        pj = project(i)["project"]
        declared = list(pj.get("dependencies", []))
        for extra in (pj.get("optional-dependencies") or {}).values():
            declared += list(extra)
        deps = {re.split(r"[<>=!\[ ]", d)[0] for d in declared}
        mods = imports(i)
        for d in sorted(deps - RUNTIME_ONLY[i]):
            if ALIAS.get(d, d.replace("-", "_")) not in mods:
                fail(f"{i}: declares {d} and imports it nowhere")
        third = mods - set(sys.stdlib_module_names) - {i} - {"pytest", "jsonschema"}
        for m in sorted(third):
            if not any(ALIAS.get(d, d.replace("-", "_")) == m for d in deps):
                fail(f"{i}: imports {m} and declares it nowhere -- the built image will not have it")


def the_readme_and_the_tree_agree(fail):
    for i in IMAGES:
        image = os.path.join(ROOT, "images", i)
        cited = re.findall(r"`([^`\s]+/[^`\s]+)`", read(os.path.join(image, "README.md")))
        for c in cited:
            if "<" in c or "{" in c or c.startswith(("/", "http", "~")):
                continue
            if not os.path.exists(os.path.join(image, c)) and not os.path.exists(os.path.join(ROOT, c)):
                fail(f"{i}/README.md cites {c}, which is not there")


def the_describe_and_the_code_agree(fail):
    """A model image records the knobs it read; what it leaves out never reaches an identity."""
    for i in ("vlm",):
        src = read(os.path.join(pkg(i), "serve.py"))
        named = set()
        for key in ("DESCRIBED", "NOT_DESCRIBED"):
            hit = re.search(rf'^{key} = \(([^)]*)\)', src, re.M)
            if not hit:
                fail(f"{i}: serve.py declares no {key}")
                continue
            named |= {x for x in re.split(r'[,\s"]+', hit.group(1)) if x}
        described = named
        for n in sorted(knobs_read(i) - {x.strip() for x in described if x.strip()}):
            fail(f"{i}: reads {n} and the describe never carries it, so it never reaches an identity")


def the_lock_and_the_images_agree(fail):
    """What CI resolved is what the image installs: a stale constraints file ships untested versions."""
    import subprocess

    for i in IMAGES:
        c = os.path.join(ROOT, "images", i, "constraints.txt")
        if not os.path.exists(c):
            fail(f"{i}: no constraints.txt, so the image resolves fresh and ships what no test saw")
            continue
        if i == "vlm":
            continue  # pinned by hand against a CUDA wheel index, not derivable from the lock
        cmd = ["uv", "export", "--package", i, "--no-dev", "--no-emit-project", "--locked",
               "--no-hashes", "-o", f"images/{i}/constraints.txt"]
        if i == "layout":
            cmd.insert(4, "--all-extras")
        got = subprocess.run(cmd[:-2] + ["--quiet"], cwd=ROOT, capture_output=True, text=True)
        if got.returncode:
            fail(f"{i}: uv export failed: {got.stderr.strip()[:120]}")
            continue
        dockerfile = read(os.path.join(ROOT, "images", i, "Dockerfile"))
        installs = [l for l in dockerfile.split("\n") if "uv pip install" in l and "huggingface" not in l]
        if not any("-c constraints.txt" in l or "-c /tmp/constraints.txt" in l for l in installs):
            fail(f"{i}: the Dockerfile installs without -c constraints.txt, so the lock does not reach the image")
        want = [l for l in got.stdout.split("\n") if l and not l.startswith("#")]
        have = [l for l in read(c).split("\n") if l and not l.startswith("#")]
        if want != have:
            fail(f"{i}: constraints.txt is not what uv.lock resolves; regenerate it ({' '.join(cmd)})")


def main():
    bad = []
    checks = (no_image_reaches_another, the_registry_and_the_code_agree,
              the_dependencies_and_the_imports_agree, the_readme_and_the_tree_agree,
              the_describe_and_the_code_agree, the_lock_and_the_images_agree)
    for check in checks:
        check(bad.append)
    for line in bad:
        print(line)
    print(f"{len(checks)} agreements over {len(IMAGES)} images: {len(bad)} broken")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
