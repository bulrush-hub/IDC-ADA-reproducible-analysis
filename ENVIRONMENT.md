# IDC modeling environment

All Python dependencies must be installed into the project-local `.venv`.
Do not install packages into the system or global Python environment.

The TabPFN comparison uses a second project-local environment,
`.venv-tabpfn`, so that the large PyTorch/TabPFN dependency stack cannot alter
the locked baseline modeling environment. Both environments are local to this
project and both must be recreated, rather than copied, when migrating to
Linux.

The `.venv` directory is operating-system-specific and must not be copied from
Windows to Linux. Migrate the project files and dependency manifests, then
recreate the environment on the target operating system.

## Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-modeling.lock.txt
```

## Linux

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements-modeling.lock.txt
```

Use the environment interpreter directly when running the workflow:

```bash
./.venv/bin/python work/run_modeling_pipeline.py
```

On Windows, replace `./.venv/bin/python` with
`.\.venv\Scripts\python.exe`.

## TabPFN environment

TabPFN-3 model weights require one-time acceptance of the Prior Labs
non-commercial license. Visit `https://ux.priorlabs.ai/`, accept the license,
create an API key, copy `.env.example` to `.env`, and replace the placeholder.
The `.env` file is ignored by Git and must never be included in a shared
archive.

### Windows

```powershell
C:\path\to\python3.12\python.exe -m venv .venv-tabpfn
.\.venv-tabpfn\Scripts\python.exe -m pip install -r requirements-tabpfn.lock.txt
.\.venv-tabpfn\Scripts\python.exe outputs\IDC_TabPFN_pipeline.py
```

If Windows reports a path-too-long error while installing PyTorch, temporarily
map the project to a short drive letter and run the same installation through
that path. The environment still remains physically inside the project.

### Linux

```bash
python3.12 -m venv .venv-tabpfn
./.venv-tabpfn/bin/python -m pip install -r requirements-tabpfn.lock.txt
./.venv-tabpfn/bin/python outputs/IDC_TabPFN_pipeline.py
```

The pipeline stores downloaded TabPFN checkpoints under
`work/tabpfn_model_cache`; it does not install Python packages globally.
