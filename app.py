# File: app.py

```python
import os
import warnings
import urllib.request

import numpy as np
import pandas as pd

from bokeh.io import curdoc
from bokeh.layouts import column
from bokeh.models import (
    BasicTicker,
    ColorBar,
    ColumnDataSource,
    CustomJS,
    DataTable,
    Div,
    FactorRange,
    HoverTool,
    LinearColorMapper,
    NumberFormatter,
    PrintfTickFormatter,
    RadioButtonGroup,
    Range1d,
    RangeSlider,
    Select,
    TableColumn,
)
from bokeh.palettes import RdYlGn11
from bokeh.plotting import figure
from bokeh.transform import factor_cmap

warnings.filterwarnings("ignore")


BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/"
FILES = {
    "DEMO": "DEMO_L.XPT",
    "BMX": "BMX_L.XPT",
    "BPX": "BPXO_L.XPT",
    "DIQ": "DIQ_L.XPT",
    "SMQ": "SMQ_L.XPT",
}

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


for key, filename in FILES.items():
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        urllib.request.urlretrieve(BASE_URL + filename, path)


raw = {
    key: pd.read_sas(os.path.join(DATA_DIR, filename))
    for key, filename in FILES.items()
}


df = raw["DEMO"].copy()
for name in ["BMX", "BPX", "DIQ", "SMQ"]:
    df = df.merge(raw[name], on="SEQN", how="left", suffixes=("", f"_{name}"))


keep = {
    "SEQN": "id",
    "RIDAGEYR": "age",
    "RIAGENDR": "gender",
    "RIDRETH3": "race",
    "DMDEDUC2": "education",
    "BMXBMI": "bmi",
    "BMXWAIST": "waist_cm",
    "BPXOSY1": "sbp",
    "BPXODI1": "dbp",
    "DIQ010": "diabetes",
    "SMQ020": "smoked_100",
}


df = df[list(keep.keys())].rename(columns=keep)


gender_map = {
    1: "Male",
    2: "Female",
}

race_map = {
    1: "Mexican American",
    2: "Other Hispanic",
    3: "Non-Hispanic White",
    4: "Non-Hispanic Black",
    6: "Non-Hispanic Asian",
    7: "Other / Multiracial",
}

education_map = {
    1: "Less than 9th grade",
    2: "9–11th grade",
    3: "High school / GED",
    4: "Some college",
    5: "College graduate+",
}


df["gender"] = df["gender"].map(gender_map)
df["race"] = df["race"].map(race_map)
df["education"] = df["education"].map(education_map)


df["diabetes_status"] = df["diabetes"].map({1: "Yes", 2: "No", 3: "Borderline"})
df["ever_smoked"] = df["smoked_100"].map({1: "Yes", 2: "No"})


def bmi_category(b):
    if pd.isna(b):
        return np.nan
    if b < 18.5:
        return "Underweight"
    if b < 25:
        return "Normal"
    if b < 30:
        return "Overweight"
    return "Obese"


age_bins = [0, 18, 35, 50, 65, 120]
age_labels = ["0–17", "18–34", "35–49", "50–64", "65+"]


df["age_group"] = pd.cut(
    df["age"],
    bins=age_bins,
    labels=age_labels,
    right=False,
)


df["bmi_cat"] = df["bmi"].apply(bmi_category)


df["hypertension"] = np.where(df["sbp"] >= 130, "Hypertensive", "Normal")


# =============================
# 5.1 Scatter Plot
# =============================

scatter_df = df.dropna(subset=["bmi", "sbp", "age", "gender"]).copy()
scatter_df["color"] = scatter_df["gender"].map(
    {
        "Male": "#2166ac",
        "Female": "#d6604d",
    }
)

full_source = ColumnDataSource(scatter_df)
plot_source = ColumnDataSource(scatter_df.copy())

p1 = figure(
    title="BMI vs. Systolic Blood Pressure",
    x_axis_label="Body Mass Index (kg/m²)",
    y_axis_label="Systolic Blood Pressure (mmHg)",
    tools=[
        HoverTool(
            tooltips=[
                ("Age", "@age"),
                ("BMI", "@bmi{0.0}"),
                ("SBP", "@sbp{0.0}"),
                ("Gender", "@gender"),
            ]
        ),
        "pan",
        "wheel_zoom",
        "box_zoom",
        "reset",
    ],
    width=750,
    height=430,
    toolbar_location="above",
)

p1.scatter(
    "bmi",
    "sbp",
    source=plot_source,
    color="color",
    alpha=0.45,
    size=5,
    legend_field="gender",
)

p1.add_layout(p1.legend[0], "right")
p1.legend.title = "Sex"

p1.line([18.5, 18.5], [60, 200], color="gray", line_dash="dashed", line_width=1, alpha=0.6)
p1.line([25.0, 25.0], [60, 200], color="gray", line_dash="dashed", line_width=1, alpha=0.6)
p1.line([30.0, 30.0], [60, 200], color="gray", line_dash="dashed", line_width=1, alpha=0.6)
p1.line([10, 70], [130, 130], color="#d6604d", line_dash="dashed", line_width=1, alpha=0.5)

age_slider = RangeSlider(
    title="Age range (years)",
    start=0,
    end=80,
    value=(0, 80),
    step=1,
    width=600,
)

callback = CustomJS(
    args=dict(full=full_source, plot=plot_source, slider=age_slider),
    code="""
    const [lo, hi] = slider.value;
    const fd = full.data;
    const keys = Object.keys(fd);
    const pd = {};
    keys.forEach(k => pd[k] = []);

    for (let i = 0; i < fd['age'].length; i++) {
        if (fd['age'][i] >= lo && fd['age'][i] <= hi) {
            keys.forEach(k => pd[k].push(fd[k][i]));
        }
    }

    plot.data = pd;
    plot.change.emit();
""",
)

age_slider.js_on_change("value", callback)


# =============================
# 5.2 Diabetes Bar Chart
# =============================


diab_df = df.dropna(subset=["diabetes_status", "race", "gender"]).copy()
diab_df = diab_df[diab_df["diabetes_status"] == "Yes"]


total_by_group = (
    df.dropna(subset=["diabetes_status", "race", "gender"])
    .groupby(["race", "gender"])
    .size()
    .reset_index(name="total")
)

cases_by_group = (
    diab_df.groupby(["race", "gender"])
    .size()
    .reset_index(name="cases")
)

prev = total_by_group.merge(cases_by_group, on=["race", "gender"])
prev["cases"] = prev["cases"].fillna(0)
prev["prevalence_pct"] = (prev["cases"] / prev["total"] * 100).round(1)
prev["x"] = list(zip(prev["race"], prev["gender"]))

races = sorted(prev["race"].unique())
genders = ["Male", "Female"]
factors = [(r, g) for r in races for g in genders]

prev_sorted = (
    prev.set_index(["race", "gender"])
    .reindex(pd.MultiIndex.from_tuples(factors))
    .reset_index()
)

prev_sorted = prev_sorted.rename(columns={"level_0": "race", "level_1": "gender"})
prev_sorted["x"] = [(r, g) for r, g in zip(prev_sorted["race"], prev_sorted["gender"])]
prev_sorted = prev_sorted.fillna(0)

source2 = ColumnDataSource(prev_sorted)

p2 = figure(
    x_range=FactorRange(*factors),
    title="Diabetes Prevalence (%) by Race/Ethnicity and Sex — hover for details",
    x_axis_label="Race/Ethnicity and Sex",
    y_axis_label="Prevalence (%)",
    tools=[
        "pan",
        "wheel_zoom",
        "reset",
        HoverTool(
            tooltips=[
                ("Group", "@race — @gender"),
                ("Cases", "@cases{0}"),
                ("Total", "@total{0}"),
                ("Prevalence", "@prevalence_pct{0.1f}%"),
            ]
        ),
    ],
    width=820,
    height=430,
    toolbar_location="above",
)

palette2 = factor_cmap(
    "x",
    palette=["#2166ac", "#d6604d"],
    factors=genders,
    start=1,
    end=2,
)

p2.vbar(
    x="x",
    top="prevalence_pct",
    width=0.8,
    source=source2,
    fill_color=palette2,
    line_color="white",
    alpha=0.85,
)

p2.xaxis.major_label_orientation = 0.9
p2.y_range = Range1d(0, 25)
p2.xgrid.grid_line_color = None


# =============================
# 5.3 Box Plot
# =============================

bmi_cat = ["Underweight", "Normal", "Overweight", "Obese"]
age_groups = ["18–34", "35–49", "50–64", "65+"]
colors_bmi = ["#74add1", "#4dac26", "#f46d43", "#d73027"]


def compute_boxplot_data(age_group):
    records = []

    sub = df[
        df["age_group"].a
```
