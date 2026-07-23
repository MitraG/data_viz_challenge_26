"""
The impact of climate change on fishing in the Pacific
--------------------------------------------------------
A "scrollytelling" Streamlit app: as you scroll down the page, a sticky
chart on the right updates to reveal more of the timeline, in sync with
narrative text on the left.

"""

import json

import pandas as pd
import sdmxthon
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(layout="wide", page_title="Fishing & Climate Change in the Pacific")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def load_sea_level_data():
    """Annual sea level indicator from SPC's climate change dataset, averaged
    across reporting Pacific countries/territories for each year.
    """
    url = (
        "https://stats-sdmx-disseminate.pacificdata.org/rest/data/"
        "SPC,DF_CLIMATE_CHANGE,1.0/A..?startPeriod=2000&endPeriod=2026"
    )
    try:
        msg = sdmxthon.read_sdmx(url)
        df = msg.content["SPC:DF_CLIMATE_CHANGE(1.0)"].data
        df = df[df["CLIMATE_CHANGE_INDICATORS"] == "SEA_LVL"].copy()
        df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
        df.dropna(subset=["OBS_VALUE"], inplace=True)

        year_col = "TIME_PERIOD" if "TIME_PERIOD" in df.columns else "OBS_TIME"
        df["year"] = pd.to_numeric(df[year_col], errors="coerce").astype("Int64")
        df.dropna(subset=["year"], inplace=True)

        yearly = (
            df.groupby(["year"])["OBS_VALUE"]   # this is across all regions, we should probably disaggregate
            .mean()
            .reset_index()
            .rename(columns={"OBS_VALUE": "sea_level"})
        )
        yearly["year"] = yearly["year"].astype(int)
        return yearly.sort_values("year")
    except Exception as e:
        st.warning(f"Couldn't load live sea level data ({e}).")


@st.cache_data
def load_fish_data():
    """Historical coastal fisheries production. Currently a hand-entered
    placeholder (only 5 points) - swap in a real SPC catch/production
    dataset when you have one, following the same load-and-tidy pattern
    as load_sea_level_data above.
    """
    return pd.DataFrame({
        "year": [1960, 1975, 1985, 2005, 2012],
        "fish_tonnes": [32000, 55000, 108000, 155000, 165000],
    })


df_sea_level = load_sea_level_data()
df_fish = load_fish_data()


# ---------------------------------------------------------------------------
# Build the narrative steps - one per data point we want to reveal
# ---------------------------------------------------------------------------

def build_steps(df_fish: pd.DataFrame, df_sea_level: pd.DataFrame):
    """One step per year that has either a fish or a sea-level reading,
    in chronological order.
    """
    fish_map = dict(zip(df_fish["year"], df_fish["fish_tonnes"]))
    sea_map = dict(zip(df_sea_level["year"], df_sea_level["sea_level"]))
    years = sorted(set(fish_map) | set(sea_map))

    steps = []
    for y in years:
        bits = []
        if y in fish_map:
            bits.append(f"coastal fisheries production was about {fish_map[y]:,} tonnes")
        if y in sea_map:
            bits.append(f"average sea level stood at roughly {sea_map[y]:.0f} mm")
        text = f"In {y}, " + " and ".join(bits) + "." if bits else f"{y}"
        steps.append({"year": y, "headline": str(y), "text": text})
    return steps


steps = build_steps(df_fish, df_sea_level)

fish_series = [
    {"year": int(r.year), "value": float(r.fish_tonnes)} for r in df_fish.itertuples()
]
sea_series = [
    {"year": int(r.year), "value": float(r.sea_level)} for r in df_sea_level.itertuples()
]


# ---------------------------------------------------------------------------
# Page header + intro (ordinary Streamlit, above the scrolly section)
# ---------------------------------------------------------------------------

st.title("The Impact of Climate Change on Fishing in the Pacific")
st.markdown(
    "Scroll through the section below to move through time. The chart on the "
    "right builds up year by year as you go, tracking coastal fisheries "
    "production alongside sea level."
)


# ---------------------------------------------------------------------------
# The scroll-linked component
# ---------------------------------------------------------------------------

COMPONENT_HEIGHT = 720  # visible height of the scrolly section, in pixels

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {
    --bg: #f3efe6;
    --ink: #10333a;
    --muted: #5b6f73;
    --fish: #2a7f7e;
    --sea: #e07a5f;
    --panel: #ffffff;
    --rule: #d8d0bf;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; height: 100%;
    font-family: -apple-system, "Segoe UI", Inter, Arial, sans-serif;
    background: var(--bg);
    color: var(--ink);
    overflow-y: scroll;
  }
  .wrap { display: flex; align-items: flex-start; }
  .steps-col { flex: 1 1 44%; min-width: 260px; }
  .graphic-col {
    flex: 1 1 56%;
    position: sticky;
    top: 0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .panel {
    background: var(--panel);
    border: 1px solid var(--rule);
    border-radius: 10px;
    width: 100%;
    max-width: 640px;
    padding: 16px 16px 8px;
  }
  .year-label {
    font-size: 15px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 4px;
  }
  .year-label b { color: var(--ink); font-size: 20px; letter-spacing: normal; }
  .legend-row { display: flex; gap: 18px; font-size: 13px; color: var(--muted); margin-top: 4px; }
  .swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }
  .step {
    min-height: 78vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 32px 28px;
    border-left: 3px solid transparent;
    opacity: 0.4;
    transition: opacity 0.25s ease, border-color 0.25s ease;
  }
  .step.active { opacity: 1; border-left-color: var(--fish); }
  .step .step-year { font-size: 13px; color: var(--muted); letter-spacing: 0.08em; text-transform: uppercase; }
  .step h2 { margin: 6px 0 10px; font-size: 28px; }
  .step p { margin: 0; color: var(--ink); font-size: 16px; line-height: 1.5; max-width: 46ch; }
  .spacer { height: 20vh; }
</style>
</head>
<body>
  <div class="wrap">
    <div class="steps-col" id="steps">
      __STEPS_HTML__
      <div class="spacer"></div>
    </div>
    <div class="graphic-col">
      <div class="panel">
        <div class="year-label">Year <b id="year-label">__FIRST_YEAR__</b></div>
        <div id="chart" style="width:100%; height:420px;"></div>
        <div class="legend-row">
          <span><span class="swatch" style="background:var(--fish)"></span>Fish production (t)</span>
          <span><span class="swatch" style="background:var(--sea)"></span>Sea level (mm)</span>
        </div>
      </div>
    </div>
  </div>

<script>
  const FISH = __FISH_JSON__;
  const SEA = __SEA_JSON__;
  const STEPS = __STEPS_JSON__;

  function sliceUpTo(series, year) {
    return series.filter(d => d.year <= year);
  }

  function render(year) {
    const fish = sliceUpTo(FISH, year);
    const sea = sliceUpTo(SEA, year);

    const traceFish = {
      x: fish.map(d => d.year), y: fish.map(d => d.value),
      name: "Fish production (t)", mode: "lines+markers",
      line: { color: "#2a7f7e", width: 3 },
      marker: { size: 7 },
      yaxis: "y1",
    };
    const traceSea = {
      x: sea.map(d => d.year), y: sea.map(d => d.value),
      name: "Sea level (mm)", mode: "lines+markers",
      line: { color: "#e07a5f", width: 3, dash: "dot" },
      marker: { size: 7 },
      yaxis: "y2",
    };

    const layout = {
      margin: { l: 55, r: 55, t: 10, b: 35 },
      showlegend: false,
      xaxis: { title: "", range: [__X_MIN__, __X_MAX__], gridcolor: "#eee" },
      yaxis: { title: "Fish (t)", color: "#2a7f7e", rangemode: "tozero" },
      yaxis2: {
        title: "Sea level (mm)", color: "#e07a5f",
        overlaying: "y", side: "right", rangemode: "tozero",
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: "-apple-system, Segoe UI, Inter, Arial, sans-serif", color: "#10333a" },
      transition: { duration: 350, easing: "cubic-in-out" },
    };

    Plotly.react("chart", [traceFish, traceSea], layout, { displayModeBar: false, responsive: true });
    document.getElementById("year-label").textContent = year;
  }

  render(STEPS[0].year);

  const stepEls = document.querySelectorAll(".step");
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const year = parseInt(entry.target.dataset.year, 10);
        render(year);
        stepEls.forEach(s => s.classList.remove("active"));
        entry.target.classList.add("active");
      }
    });
  }, { threshold: 0.55 });
  stepEls.forEach(s => observer.observe(s));
</script>
</body>
</html>
"""

steps_html = "\n".join(
    f'<div class="step" data-year="{s["year"]}">'
    f'<div class="step-year">{s["headline"]}</div>'
    f"<h2>{s['year']}</h2>"
    f"<p>{s['text']}</p>"
    f"</div>"
    for s in steps
)

all_years = [d["year"] for d in fish_series] + [d["year"] for d in sea_series]

html = (
    HTML_TEMPLATE
    .replace("__STEPS_HTML__", steps_html)
    .replace("__FIRST_YEAR__", str(steps[0]["year"]))
    .replace("__FISH_JSON__", json.dumps(fish_series))
    .replace("__SEA_JSON__", json.dumps(sea_series))
    .replace("__STEPS_JSON__", json.dumps(steps))
    .replace("__X_MIN__", str(min(all_years) - 2))
    .replace("__X_MAX__", str(max(all_years) + 2))
)

components.html(html, height=COMPONENT_HEIGHT, scrolling=True)


# ---------------------------------------------------------------------------
# Optional: raw data below the scrolly section, using ordinary Streamlit
# ---------------------------------------------------------------------------

with st.expander("See the underlying data"):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Fish production")
        st.dataframe(df_fish, use_container_width=True)
    with col2:
        st.subheader("Sea level")
        st.dataframe(df_sea_level, use_container_width=True)