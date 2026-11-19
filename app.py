"""서울시 지하철 호선별·역별·시간대별 승하차 인원 분석 대시보드."""

from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

HERE = Path(__file__).parent

st.set_page_config(page_title="서울시 지하철 승하차 인원 대시보드", layout="wide")


@st.cache_data
def load_data():
    # 배포용 경량 파일(subway_2025_2026.csv)을 우선 찾고, 없으면 원본 CSV를 읽습니다.
    light_path = HERE / "subway_2025_2026.csv"
    raw_path = HERE / "서울시 지하철 호선별 역별 시간대별 승하차 인원 정보.csv"

    if light_path.exists():
        df = pd.read_csv(light_path, encoding="utf-8-sig")
    elif raw_path.exists():
        try:
            df = pd.read_csv(raw_path, encoding="cp949")
        except UnicodeDecodeError:
            df = pd.read_csv(raw_path, encoding="utf-8-sig")
    else:
        raise FileNotFoundError("데이터 CSV 파일을 찾을 수 없습니다.")

    df["사용월_str"] = df["사용월"].astype(str)
    df["연월"] = df["사용월_str"].str[:4] + "-" + df["사용월_str"].str[4:6]

    ride_cols = [c for c in df.columns if "승차인원" in c]
    alight_cols = [c for c in df.columns if "하차인원" in c]

    df["총승차인원"] = df[ride_cols].sum(axis=1)
    df["총하차인원"] = df[alight_cols].sum(axis=1)
    df["총이용인원"] = df["총승차인원"] + df["총하차인원"]
    return df


st.title("🚇 서울시 지하철 호선별·역별·시간대별 승하차 인원 분석")
st.caption("출처: 서울 열린데이터광장 (서울시 지하철 호선별 역별 시간대별 승하차 인원 정보) · 단위: 명")

try:
    data = load_data()
except FileNotFoundError:
    st.error("app.py와 같은 폴더에 `subway_2025_2026.csv` 또는 원본 CSV 파일을 올려 주세요.")
    st.stop()

# --- 사이드바 조회 조건 ---
st.sidebar.header("조회 조건")

all_months = sorted(data["연월"].unique())
selected_months = st.sidebar.multiselect(
    "사용월 선택",
    options=all_months,
    default=[all_months[-1]] if len(all_months) > 0 else [],
)

all_lines = sorted(data["호선명"].unique())
default_lines = [line for line in ["1호선", "2호선", "3호선", "4호선"] if line in all_lines]
selected_lines = st.sidebar.multiselect(
    "호선 선택",
    options=all_lines,
    default=default_lines if default_lines else all_lines[:3],
)

metric_label = st.sidebar.selectbox("표시 지표", ["총이용인원", "총승차인원", "총하차인원"])

# --- 데이터 필터링 ---
view = data.loc[
    data["연월"].isin(selected_months) & data["호선명"].isin(selected_lines)
].copy()

if view.empty:
    st.warning("표시할 데이터가 없습니다. 사용월과 호선을 하나 이상 선택하세요.")
    st.stop()

# --- 상단 지표 카드 ---
st.subheader(f"선택 조건 요약 ({len(selected_months)}개월 · {len(selected_lines)}개 호선)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("총 이용인원 (승차+하차)", f"{view['총이용인원'].sum():,.0f} 명")
c2.metric("총 승차인원", f"{view['총승차인원'].sum():,.0f} 명")
c3.metric("총 하차인원", f"{view['총하차인원'].sum():,.0f} 명")
c4.metric("조회 역 수 (중복 제외)", f"{view['지하철역'].nunique():,.0f} 개")

st.divider()

# --- 차트 1 & 차트 2: 호선별 비교 & 상위 10개 역 ---
left, right = st.columns(2)

with left:
    line_sum = view.groupby("호선명", as_index=False)[metric_label].sum().sort_values(metric_label, ascending=False)
    fig_line = px.bar(
        line_sum,
        x="호선명",
        y=metric_label,
        color="호선명",
        text_auto=".2s",
        title=f"호선별 {metric_label} 합계",
        labels={"호선명": "호선", metric_label: f"{metric_label} (명)"},
    )
    fig_line.update_layout(showlegend=False)
    st.plotly_chart(fig_line, use_container_width=True)

with right:
    station_sum = (
        view.groupby(["호선명", "지하철역"], as_index=False)[metric_label]
        .sum()
        .sort_values(metric_label, ascending=False)
        .head(10)
    )
    station_sum["역_호선"] = station_sum["지하철역"] + " (" + station_sum["호선명"] + ")"
    fig_station = px.bar(
        station_sum.sort_values(metric_label, ascending=True),
        x=metric_label,
        y="역_호선",
        orientation="h",
        color="호선명",
        text_auto=".2s",
        title=f"{metric_label} 상위 10개 역",
        labels={"역_호선": "지하철역", metric_label: f"{metric_label} (명)", "호선명": "호선"},
    )
    st.plotly_chart(fig_station, use_container_width=True)

# --- 차트 3: 시간대별 승차 vs 하차 패턴 ---
st.subheader("⏰ 시간대별 승차·하차 추이")
target_station = st.selectbox(
    "특정 역 시간대 패턴 보기 (전체 선택 시 조회된 전체 역 합계)",
    options=["전체 조회 역 합계"] + sorted(view["지하철역"].unique()),
)

if target_station == "전체 조회 역 합계":
    time_df = view
else:
    time_df = view[view["지하철역"] == target_station]

hours = [f"{h:02d}시-{(h+1)%24:02d}시" for h in list(range(4, 24)) + list(range(0, 4))]
time_rows = []
for h_str in hours:
    r_col = f"{h_str} 승차인원"
    a_col = f"{h_str} 하차인원"
    if r_col in time_df.columns and a_col in time_df.columns:
        time_rows.append({"시간대": h_str, "구분": "승차인원", "인원": time_df[r_col].sum()})
        time_rows.append({"시간대": h_str, "구분": "하차인원", "인원": time_df[a_col].sum()})

time_long = pd.DataFrame(time_rows)
fig_time = px.line(
    time_long,
    x="시간대",
    y="인원",
    color="구분",
    markers=True,
    color_discrete_map={"승차인원": "#0072B2", "하차인원": "#D55E00"},
    title=f"시간대별 승·하차 인원 추이 ({target_station})",
    labels={"시간대": "시간대", "인원": "인원 (명)", "구분": "구분"},
)
fig_time.update_layout(hovermode="x unified")
fig_time.update_xaxes(tickangle=-45)
st.plotly_chart(fig_time, use_container_width=True)

# --- 상세 데이터 표 및 CSV 다운로드 ---
with st.expander("📋 필터링된 상세 데이터 보기 및 CSV 다운로드"):
    display_cols = ["사용월", "연월", "호선명", "지하철역", "총승차인원", "총하차인원", "총이용인원"]
    st.dataframe(view[display_cols], hide_index=True, use_container_width=True)
    st.download_button(
        "현재 선택 요약 데이터 CSV 저장",
        data=view[display_cols].to_csv(index=False).encode("utf-8-sig"),
        file_name="subway_filtered.csv",
        mime="text/csv",
    )
