import json
import os
from pathlib import Path

notebook = Path("../outputs/IDC_Clean_cleaned_annotated_corrected.ipynb")
nb = json.loads(notebook.read_text(encoding="utf-8"))
code_cells = ["".join(c.get("source", [])) for c in nb["cells"] if c.get("cell_type") == "code"]
for i, source in enumerate(code_cells):
    compile(source, f"cell_{i}", "exec")

# Execute through MOA classification/review (before plotting) against the corrected workbook.
run_dir = Path("notebook_smoke_test")
run_dir.mkdir(exist_ok=True)
source_book = Path("../outputs/IDC_modeling_table_cleaned_annotated_corrected.xlsx").resolve()
target_book = run_dir / "IDC_modeling_table_cleaned_annotated.xlsx"
if not target_book.exists():
    target_book.write_bytes(source_book.read_bytes())

os.chdir(run_dir)
namespace = {"display": lambda *args, **kwargs: None}
executed = 0
for cell in nb["cells"]:
    if cell.get("cell_type") != "code":
        continue
    source = "".join(cell.get("source", []))
    if "# 输出仍需复核的 MOA" in source:
        break
    if "plt." in source:
        continue
    source = source.replace("import matplotlib.pyplot as plt\n", "")
    exec(compile(source, f"smoke_cell_{executed}", "exec"), namespace)
    executed += 1

df = namespace["df"]
assert not ((df["molecule_inn_name"] == "Bevacizumab") & (df["target_clean"] == "CD22")).any()
expected = {
    "Cetuximab": "Receptor blockade/antagonism",
    "Necitumumab": "Receptor blockade/antagonism",
    "Reslizumab": "Receptor blockade/antagonism",
    "GSK3174998": "Receptor agonism",
    "Utomilumab": "Receptor agonism",
    "Faricimab": "Ligand neutralization",
    "Trebananib": "Ligand neutralization",
    "Isatuximab": "Immune-cell targeting/modulation",
}
for molecule, group in expected.items():
    actual = set(df.loc[df["molecule_inn_name"].eq(molecule), "moa_group"].dropna())
    assert actual == {group}, (molecule, actual, group)
faricimab = set(df.loc[df["molecule_inn_name"].eq("Faricimab"), "mechanism_of_action_reviewed"])
assert faricimab and all(not str(v).rstrip().endswith(" by") for v in faricimab)
print({"compiled_code_cells": len(code_cells), "executed_code_cells": executed, "rows_after_exact_dedup": len(df), "checks": "PASS"})
