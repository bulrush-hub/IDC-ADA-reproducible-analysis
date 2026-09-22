import json
import os
from pathlib import Path

nb = json.loads(Path("../outputs/IDC_Clean_final_model_ready.ipynb").read_text(encoding="utf-8"))
codes = ["".join(c.get("source", [])) for c in nb["cells"] if c.get("cell_type") == "code"]
for i, code in enumerate(codes):
    compile(code, f"cell_{i}", "exec")

run = Path("final_notebook_smoke")
run.mkdir(exist_ok=True)
book = run / "IDC_modeling_table_cleaned_annotated.xlsx"
book.write_bytes(Path("../outputs/IDC_modeling_table_cleaned_annotated_corrected.xlsx").read_bytes())
os.chdir(run)
ns = {"display": lambda *args, **kwargs: None}
executed = 0
for i, cell in enumerate(nb["cells"]):
    if cell.get("cell_type") != "code":
        continue
    code = "".join(cell.get("source", []))
    if "plt." in code or "save_distribution_plot(" in code or "save_ADA_rate_plot(" in code:
        continue
    code = code.replace("import matplotlib.pyplot as plt\n", "")
    exec(compile(code, f"run_cell_{i}", "exec"), ns)
    executed += 1
    if "# ---------- 最终人工审核决定与建模前处理 ----------" in code:
        break

m = ns["modeling_df"]
assert len(m) == 2611
assert m["idc_row_id"].is_unique
assert not m["moa_group"].isin(["Other/unclear", "Missing"]).any()
assert set(m.loc[m["molecule_inn_name"].eq("Reslizumab"), "moa_group"]) == {"Ligand neutralization"}
assert not (m["molecule_inn_name"].eq("Bevacizumab") & m["target_clean"].eq("CD22")).any()
assert int(m["binomial_count_model_eligible"].sum()) == 2506
print({"compiled_cells":len(codes),"executed_cells":executed,"rows":len(m),"unique_ids":m.idc_row_id.nunique(),"status":"PASS"})
