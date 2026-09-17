import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io, re, urllib.parse, urllib.request

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Egg Hatching Dashboard",
    page_icon="🥚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main { background-color: #f7f9fc; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    h1, h2, h3 { color: #1f3b57; }
    .metric-card {
        background: linear-gradient(135deg, #ffffff 0%, #f0f4ff 100%);
        border-radius: 16px; padding: 18px 20px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.06);
        border-left: 6px solid #4f8bf9;
    }
    .metric-card h4 { margin: 0; color: #6b7a90; font-size: 0.85rem; font-weight: 600; letter-spacing:.5px;}
    .metric-card h2 { margin: 6px 0 0 0; color: #1f3b57; font-size: 1.7rem; font-weight: 700; }
    .metric-card p  { margin: 4px 0 0 0; font-size: 0.8rem; }
    .stPlotlyChart { border-radius: 14px; }
</style>
""", unsafe_allow_html=True)


# ---------------- LOADING LOGIC ----------------
def _sheet_id_from_url(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise ValueError("Invalid Google Sheet URL")
    return m.group(1)


def _read_public_tab(url: str, tab_name: str) -> pd.DataFrame:
    """Read a public Google Sheet tab via the gviz CSV endpoint."""
    sheet_id = _sheet_id_from_url(url)
    tab_q = urllib.parse.quote(tab_name)
    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={tab_q}"
    )
    with urllib.request.urlopen(csv_url) as r:
        return pd.read_csv(io.StringIO(r.read().decode("utf-8")))


def _read_private_tab(url: str, tab_name: str) -> pd.DataFrame:
    """Read a private Google Sheet tab using a service account."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    client = gspread.authorize(creds)
    ws = client.open_by_url(url).worksheet(tab_name)
    return pd.DataFrame(ws.get_all_records())


@st.cache_data(ttl=300, show_spinner="Fetching data from Google Sheets...")
def load_both_sheets():
    """Try private first, fall back to public gviz. Then fall back to sample data."""
    url = st.secrets.get("sheet", {}).get("url", "") if hasattr(st, "secrets") else ""
    hatchery_tab = "Cycle_INFO_Hatchery"
    farm_tab     = "Cycle_INFO_Farm"

    try:
        if url:
            try:
                hatchery_tab = st.secrets["sheet"].get("hatchery_tab", hatchery_tab)
                farm_tab     = st.secrets["sheet"].get("farm_tab", farm_tab)
            except Exception:
                pass
            try:
                return _read_private_tab(url, hatchery_tab), _read_private_tab(url, farm_tab)
            except Exception as e_priv:
                try:
                    return _read_public_tab(url, hatchery_tab), _read_public_tab(url, farm_tab)
                except Exception as e_pub:
                    st.warning(f"⚠️ Falling back to sample data.\nPrivate: {e_priv}\nPublic: {e_pub}")
    except Exception as e:
        st.warning(f"⚠️ Using sample data (reason: {e})")

    # ---------- SAMPLE DATA ----------
    hatchery = pd.DataFrame({
        "Cycle": [f"Cycle-{i}" for i in range(1, 12)],
        "EGGS RECIVED": [224550,233100,233100,233100,233100,233100,234360,235620,235620,233100,233100],
        "NO. of eggs cracked/damaged": [2529,2153,2226,4200,4127,2583,2133,2783,2932,2130,3180],
        "Crack %": ["1.13%","0.92%","0.95%","1.80%","1.77%","1.11%","0.91%","1.18%","1.24%","0.91%","1.36%"],
        "No. of Eggs Setted": [222021,231182,230874,228900,228973,230517,232227,232837,232688,230970,229920],
        "Hatching Loss": [26973,22995,27191,27650,35384,29783,26908,23526,32181,25884,35330],
        "No. of chicks hatched": [195755,208187,203683,201250,193589,200734,205319,209311,200507,205086,194590],
        "Hatching%": ["87.18%","89.31%","87.38%","86.34%","83.05%","86.11%","87.61%","88.83%","85.10%","87.98%","83.48%"],
    })
    farm = pd.DataFrame({
        "Cycle": [f"Cycle-{i}" for i in range(1, 12)],
        "Culls & Vaccine mortality": [1822,1761,2125,2213,3065,2561,2557,2180,2646,2761,3040],
        "Chicks Placed": [193933,206426,201558,199037,190524,198173,202762,207131,197861,202325,191550],
        "Placement %": ["86.00%","89.00%","86.00%","85.00%","82.00%","85.02%","86.52%","87.91%","83.97%","86.80%","82.18%"],
    })
    return hatchery, farm


# ---------------- CLEANING ----------------
def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    for c in df.columns:
        if "%" in c:
            df[c] = (
                df[c].astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", "", regex=False)
                .astype(float)
            )

    for c in df.select_dtypes(include="object").columns:
        if c == "Cycle":
            continue
        cleaned = df[c].astype(str).str.replace(",", "", regex=False)
        try:
            df[c] = pd.to_numeric(cleaned)
        except Exception:
            pass

    if "Cycle" in df.columns:
        df["_n"] = df["Cycle"].astype(str).str.extract(r"(\d+)").astype(float)
        df = df.sort_values("_n").drop(columns="_n").reset_index(drop=True)
    return df


# ---------------- LOAD + MERGE ----------------
hatchery_raw, farm_raw = load_both_sheets()
hatchery = clean(hatchery_raw)
farm     = clean(farm_raw)

df = pd.merge(hatchery, farm, on="Cycle", how="outer", suffixes=("", "_farm"))

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("## 🥚 Filters")
    all_cycles = df["Cycle"].dropna().tolist()
    selected_cycles = st.multiselect(
        "Select Cycle(s)", options=all_cycles, default=all_cycles,
        help="Filter across both Hatchery & Farm data",
    )

    st.markdown("---")
    st.markdown("### 📊 Metrics to compare")
    metric_options = [c for c in df.columns
                      if c != "Cycle" and df[c].dtype != "object"]
    default_metrics = [m for m in ["No. of chicks hatched", "Hatching Loss",
                                    "Chicks Placed"] if m in metric_options]
    selected_metrics = st.multiselect(
        "Choose metrics", options=metric_options, default=default_metrics,
    )

    st.markdown("---")
    st.caption("🔗 Source: **Cycle_INFO_Hatchery** + **Cycle_INFO_Farm**")
    st.caption("Data refreshes every 5 minutes.")

if not selected_cycles:
    st.warning("Please select at least one cycle from the sidebar.")
    st.stop()

fdf = df[df["Cycle"].isin(selected_cycles)].copy()

# ---------------- HEADER ----------------
st.markdown("# 🥚 Egg Hatching Dashboard")
st.markdown("#### Hatchery + Farm cycle-wise performance")
st.markdown("---")


# ---------------- KPI CARDS ----------------
def kpi(label, value, delta=None, delta_color="#4f8bf9"):
    d = f"<p style='color:{delta_color};'>{delta}</p>" if delta else ""
    st.markdown(f"""
    <div class="metric-card">
        <h4>{label}</h4>
        <h2>{value}</h2>
        {d}
    </div>""", unsafe_allow_html=True)


def s(col, default=0):
    return fdf[col].sum() if col in fdf.columns else default

def m(col, default=0):
    return fdf[col].mean() if col in fdf.columns else default

c1, c2, c3, c4 = st.columns(4)
with c1: kpi("🥚 Total Eggs Received", f"{int(s('EGGS RECIVED')):,}")
with c2: kpi("🪺 Eggs Set", f"{int(s('No. of Eggs Setted')):,}")
with c3: kpi("🐣 Chicks Hatched", f"{int(s('No. of chicks hatched')):,}",
             f"Avg Hatching {m('Hatching%'):.2f}%", "#2ca02c")
with c4: kpi("📦 Chicks Placed", f"{int(s('Chicks Placed')):,}",
             f"Avg Placement {m('Placement %'):.2f}%", "#2ca02c")

st.markdown("<br>", unsafe_allow_html=True)

c5, c6, c7, c8 = st.columns(4)
with c5: kpi("⚠️ Avg Crack %", f"{m('Crack %'):.2f}%", None, "#d62728")
with c6: kpi("❌ Total Hatching Loss", f"{int(s('Hatching Loss')):,}")
with c7: kpi("💀 Culls & Mortality", f"{int(s('Culls & Vaccine mortality')):,}")
with c8: kpi("📈 Hatching Efficiency", f"{m('Hatching%'):.2f}%")

st.markdown("<br>", unsafe_allow_html=True)


# ---------------- CHART 1: Trends ----------------
st.markdown("### 📈 Efficiency Trends by Cycle")
fig1 = go.Figure()
if "Hatching%" in fdf: fig1.add_trace(go.Scatter(
    x=fdf["Cycle"], y=fdf["Hatching%"], mode="lines+markers",
    name="Hatching %", line=dict(color="#4f8bf9", width=3),
    marker=dict(size=10, line=dict(width=2, color="white"))))
if "Placement %" in fdf: fig1.add_trace(go.Scatter(
    x=fdf["Cycle"], y=fdf["Placement %"], mode="lines+markers",
    name="Placement %", line=dict(color="#2ca02c", width=3),
    marker=dict(size=10, line=dict(width=2, color="white"))))
if "Crack %" in fdf: fig1.add_trace(go.Scatter(
    x=fdf["Cycle"], y=fdf["Crack %"], mode="lines+markers",
    name="Crack %", line=dict(color="#d62728", width=3, dash="dot"),
    marker=dict(size=8)))
fig1.update_layout(
    template="plotly_white", height=420,
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    yaxis_title="Percentage (%)", hovermode="x unified",
)
st.plotly_chart(fig1, use_container_width=True)


# ---------------- CHART 2: Grouped Bar ----------------
if selected_metrics:
    st.markdown("### 📊 Volume Comparison (Hatchery vs Farm)")
    melted = fdf.melt(id_vars="Cycle", value_vars=selected_metrics,
                      var_name="Metric", value_name="Value")
    fig2 = px.bar(melted, x="Cycle", y="Value", color="Metric",
                  barmode="group", color_discrete_sequence=px.colors.qualitative.Set2)
    fig2.update_layout(
        template="plotly_white", height=420,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis_title="Count",
    )
    st.plotly_chart(fig2, use_container_width=True)


# ---------------- ROW: Donut + Bar ----------------
col_a, col_b = st.columns(2)

with col_a:
    st.markdown("### 🥧 Loss Composition")
    loss_cols = [c for c in ["NO. of eggs cracked/damaged", "Hatching Loss",
                              "Culls & Vaccine mortality"] if c in fdf.columns]
    if loss_cols:
        loss_data = fdf.melt(id_vars="Cycle", value_vars=loss_cols,
                             var_name="Loss Type", value_name="Count")
        fig3 = px.pie(loss_data, names="Loss Type", values="Count",
                      hole=0.55,
                      color_discrete_sequence=["#ff9f40", "#d62728", "#8c564b"])
        fig3.update_traces(textposition="outside", textinfo="percent+label")
        fig3.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10),
                           showlegend=False)
        st.plotly_chart(fig3, use_container_width=True)

with col_b:
    st.markdown("### 🐣 Hatching % per Cycle")
    if "Hatching%" in fdf:
        fig4 = px.bar(fdf, x="Cycle", y="Hatching%",
                      color="Hatching%", color_continuous_scale="Blues",
                      text="Hatching%")
        fig4.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
        fig4.update_layout(template="plotly_white", height=420,
                           margin=dict(l=10, r=10, t=30, b=10),
                           coloraxis_showscale=False, yaxis_title="Hatching %")
        st.plotly_chart(fig4, use_container_width=True)


# ---------------- DATA TABLES (per source) ----------------
st.markdown("### 📋 Detailed Data")
tab1, tab2, tab3 = st.tabs(["🔗 Merged View", "🥚 Cycle_INFO_Hatchery", "🚜 Cycle_INFO_Farm"])

def styled(d):
    pct = [c for c in d.columns if "%" in c]
    num = [c for c in d.columns if c not in pct and c != "Cycle"]
    fmt = {c: "{:,.0f}" for c in num}
    st_obj = d.style.format(fmt)
    if pct:
        st_obj = st_obj.background_gradient(subset=pct, cmap="RdYlGn")
    return st_obj

with tab1: st.dataframe(styled(fdf), use_container_width=True, hide_index=True)
with tab2:
    sub = hatchery[hatchery["Cycle"].isin(selected_cycles)]
    st.dataframe(styled(sub), use_container_width=True, hide_index=True)
with tab3:
    sub = farm[farm["Cycle"].isin(selected_cycles)]
    st.dataframe(styled(sub), use_container_width=True, hide_index=True)


# ---------------- DOWNLOAD ----------------
st.download_button(
    "⬇️ Download merged filtered data as CSV",
    data=fdf.to_csv(index=False).encode("utf-8"),
    file_name="egg_hatching_merged.csv",
    mime="text/csv",
)

st.markdown("---")
st.caption("🥚 Egg Hatching Analytics • Sources: Cycle_INFO_Hatchery + Cycle_INFO_Farm")
