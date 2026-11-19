import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(page_title="Seoul Subway Insight", page_icon="🚇", layout="wide")

st.title("🚇 Seoul Subway Insight")
st.caption("서울 지하철 역별 · 시간대별 승하차 인원 분석 대시보드")

BASE_DIR = Path(__file__).parent
CANDIDATE_PATHS = [
    BASE_DIR / "data" / "subway_ridership.csv",
    BASE_DIR / "subway_ridership.csv",
    BASE_DIR / "subway_data.csv",
    BASE_DIR / "subway_2025_2026.csv",
]


@st.cache_data(show_spinner="데이터를 자동으로 불러오는 중입니다...")
def load_csv():
    """저장소 내 기본 CSV 파일을 자동으로 찾아 읽고 분석용 열을 생성합니다."""
    path = next((p for p in CANDIDATE_PATHS if p.exists()), None)
    if path is None:
        raise FileNotFoundError(
            "기본 CSV 파일(data/subway_ridership.csv 또는 subway_ridership.csv)을 찾지 못했습니다. "
            "app.py와 같은 폴더나 data 폴더에 CSV 파일을 올려주세요."
        )

    try:
        data = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except UnicodeDecodeError:
        data = pd.read_csv(path, encoding="cp949", low_memory=False)

    data.columns = data.columns.astype(str).str.strip()
    required = {"사용월", "호선명", "지하철역"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(
            "필수 열이 없습니다: " + ", ".join(sorted(missing))
            + " (사용월, 호선명, 지하철역 열이 필요합니다.)"
        )

    data = data.drop_duplicates().copy()
    data["사용월"] = (
        data["사용월"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    )
    data["연월"] = pd.to_datetime(data["사용월"], format="%Y%m", errors="coerce")
    data = data.dropna(subset=["연월"])

    entry_cols = sorted(
        [c for c in data.columns if re.fullmatch(r"\d{2}시-\d{2}시 승차인원", c)],
        key=lambda x: int(x[:2])
    )
    exit_cols = sorted(
        [c for c in data.columns if re.fullmatch(r"\d{2}시-\d{2}시 하차인원", c)],
        key=lambda x: int(x[:2])
    )
    if not entry_cols or not exit_cols:
        raise ValueError("시간대별 승차·하차 인원 열을 찾지 못했습니다.")

    time_labels = [c.replace(" 승차인원", "") for c in entry_cols]
    for col in entry_cols + exit_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    data["총승차"] = data[entry_cols].sum(axis=1)
    data["총하차"] = data[exit_cols].sum(axis=1)
    data["총이용"] = data["총승차"] + data["총하차"]
    data["연도"] = data["연월"].dt.year
    return data, entry_cols, exit_cols, time_labels, path.name


def hourly_summary(data, entry_cols, exit_cols, labels):
    rows = []
    for entry, exit_, label in zip(entry_cols, exit_cols, labels):
        rows.append({
            "시간대": label,
            "승차": int(data[entry].sum()),
            "하차": int(data[exit_].sum()),
        })
    return pd.DataFrame(rows)


st.sidebar.header("분석 조건")

try:
    df, entry_cols, exit_cols, time_labels, loaded_filename = load_csv()
    st.sidebar.success(f"자동 로드 완료: `{loaded_filename}`")
except Exception as exc:
    st.error(f"데이터를 불러오지 못했습니다: {exc}")
    st.stop()

min_date, max_date = df["연월"].min(), df["연월"].max()
st.sidebar.caption(f"데이터 기간: {min_date:%Y-%m} ~ {max_date:%Y-%m}")

years = sorted(df["연도"].unique().tolist())
selected_years = st.sidebar.multiselect(
    "연도 선택", years, default=years
)
lines = sorted(df["호선명"].dropna().astype(str).unique().tolist())
selected_lines = st.sidebar.multiselect(
    "노선 선택", lines, default=lines
)

filtered = df[
    df["연도"].isin(selected_years)
    & df["호선명"].astype(str).isin(selected_lines)
].copy()

if filtered.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다. 연도와 노선을 다시 선택해 주세요.")
    st.stop()

stations = sorted(filtered["지하철역"].dropna().astype(str).unique().tolist())
default_stations = stations[:min(5, len(stations))]
selected_stations = st.sidebar.multiselect(
    "비교할 역 선택", stations, default=default_stations
)

# Summary cards
total_boarding = int(filtered["총승차"].sum())
total_alighting = int(filtered["총하차"].sum())
station_count = filtered[["호선명", "지하철역"]].drop_duplicates().shape[0]
month_count = filtered["사용월"].nunique()

m1, m2, m3, m4 = st.columns(4)
m1.metric("총 승차 인원", f"{total_boarding:,}명")
m2.metric("총 하차 인원", f"{total_alighting:,}명")
m3.metric("역-노선 수", f"{station_count:,}개")
m4.metric("분석 월 수", f"{month_count:,}개월")

st.caption(
    "이 자료는 월별·역별·노선별 승하차 집계입니다. "
    "열차 내부 혼잡도나 개인별 이동 경로를 직접 나타내지는 않습니다."
)

tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 전체 현황", "🕒 시간대 분석", "🚉 역별 비교", "🔎 데이터 탐색"]
)

with tab1:
    left, right = st.columns(2)
    monthly = (
        filtered.groupby("연월", as_index=False)[["총승차", "총하차"]]
        .sum().sort_values("연월")
    )
    monthly["월"] = monthly["연월"].dt.strftime("%Y-%m")

    with left:
        st.subheader("월별 승·하차 추이")
        monthly_long = monthly.melt(
            id_vars="월", value_vars=["총승차", "총하차"],
            var_name="구분", value_name="인원"
        )
        fig = px.line(
            monthly_long, x="월", y="인원", color="구분", markers=True,
            labels={"월": "사용월", "인원": "인원(명)", "구분": "구분"}
        )
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("노선별 이용 인원")
        line_summary = (
            filtered.groupby("호선명", as_index=False)["총이용"]
            .sum().sort_values("총이용", ascending=False)
        )
        fig = px.bar(
            line_summary, x="호선명", y="총이용", color="총이용",
            color_continuous_scale="Blues",
            labels={"호선명": "노선", "총이용": "승차+하차 인원"}
        )
        fig.update_layout(coloraxis_showscale=False, xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("이용 인원이 많은 역 TOP 15")
    top = (
        filtered.groupby(["호선명", "지하철역"], as_index=False)["총이용"]
        .sum().sort_values("총이용", ascending=False).head(15)
    )
    top["역(노선)"] = top["지하철역"] + " (" + top["호선명"] + ")"
    fig = px.bar(
        top.sort_values("총이용"), x="총이용", y="역(노선)",
        orientation="h", color="총이용", color_continuous_scale="Teal",
        labels={"총이용": "승차+하차 인원", "역(노선)": "역"}
    )
    fig.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("시간대별 승차·하차 인원")
    hourly = hourly_summary(filtered, entry_cols, exit_cols, time_labels)
    hourly_long = hourly.melt(
        id_vars="시간대", value_vars=["승차", "하차"],
        var_name="구분", value_name="인원"
    )
    fig = px.line(
        hourly_long, x="시간대", y="인원", color="구분", markers=True,
        labels={"인원": "인원(명)", "시간대": "시간대"}
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("월 × 시간대 이용량 히트맵")
    heat_rows = []
    temp = filtered.copy()
    temp["월"] = temp["연월"].dt.strftime("%Y-%m")
    for entry, exit_, label in zip(entry_cols, exit_cols, time_labels):
        grouped = temp.groupby("월")[[entry, exit_]].sum().sum(axis=1)
        for month, value in grouped.items():
            heat_rows.append({"월": month, "시간대": label, "이용인원": value})
    heat = pd.DataFrame(heat_rows).pivot(
        index="시간대", columns="월", values="이용인원"
    )
    fig = px.imshow(
        heat, aspect="auto", color_continuous_scale="YlOrRd",
        labels={"x": "월", "y": "시간대", "color": "승차+하차 인원"}
    )
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("선택한 역 비교")
    if selected_stations:
        station_data = filtered[
            filtered["지하철역"].astype(str).isin(selected_stations)
        ]
        station_monthly = (
            station_data.groupby(["연월", "지하철역"], as_index=False)
            [["총승차", "총하차", "총이용"]].sum()
        )
        station_monthly["월"] = station_monthly["연월"].dt.strftime("%Y-%m")
        measure = st.radio(
            "비교 기준", ["총승차", "총하차", "총이용"], horizontal=True,
            format_func=lambda x: {
                "총승차": "승차 인원", "총하차": "하차 인원",
                "총이용": "승차+하차 인원"
            }[x]
        )
        fig = px.line(
            station_monthly, x="월", y=measure, color="지하철역",
            markers=True, labels={"월": "사용월", measure: "인원(명)"}
        )
        st.plotly_chart(fig, use_container_width=True)

        station_totals = (
            station_data.groupby("지하철역", as_index=False)
            [["총승차", "총하차", "총이용"]].sum()
        )
        st.subheader("역별 승차·하차 관계 (산점도)")
        fig = px.scatter(
            station_totals, x="총승차", y="총하차", size="총이용",
            color="지하철역", hover_name="지하철역",
            labels={"총승차": "총 승차 인원", "총하차": "총 하차 인원"}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("왼쪽에서 비교할 역을 하나 이상 선택해 주세요.")

with tab4:
    st.subheader("데이터 검색 및 다운로드")
    keyword = st.text_input("역 이름 검색", placeholder="예: 강남, 홍대입구, 서울역")
    view = filtered.copy()
    if keyword.strip():
        view = view[
            view["지하철역"].astype(str).str.contains(
                keyword.strip(), case=False, na=False
            )
        ]

    display_cols = ["사용월", "호선명", "지하철역", "총승차", "총하차", "총이용"]
    st.write(f"검색 결과: **{len(view):,}개 행**")
    st.dataframe(
        view[display_cols].sort_values(["사용월", "호선명", "지하철역"]),
        use_container_width=True, hide_index=True
    )
    st.download_button(
        "분석 결과 CSV 다운로드",
        data=view.to_csv(index=False).encode("utf-8-sig"),
        file_name="seoul_subway_analysis.csv",
        mime="text/csv"
    )

    with st.expander("데이터 구조 확인"):
        st.write(f"행 수: {len(df):,} / 열 수: {len(df.columns):,}")
        st.dataframe(df.head(10), use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "데이터 출처: 사용자가 제공한 서울시 지하철 호선별 역별 시간대별 승하차 인원 정보. "
    f"기본 제공 범위: {min_date:%Y-%m} ~ {max_date:%Y-%m}."
)
