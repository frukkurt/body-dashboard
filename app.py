import os
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import create_client


st.set_page_config(
    page_title="Body Tracker Dashboard",
    page_icon="🏋️",
    layout="wide",
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
USER_ID = os.getenv("USER_ID", "fruk")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")

BKK = ZoneInfo("Asia/Bangkok")
UTC = ZoneInfo("UTC")


if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    st.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    st.stop()


supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def check_password():
    if not DASHBOARD_PASSWORD:
        return True

    if "password_ok" not in st.session_state:
        st.session_state.password_ok = False

    if st.session_state.password_ok:
        return True

    st.title("🔐 Body Tracker Dashboard")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if password == DASHBOARD_PASSWORD:
            st.session_state.password_ok = True
            st.rerun()
        else:
            st.error("Password ไม่ถูกต้อง")

    return False


if not check_password():
    st.stop()


def local_date_to_utc_iso(d: date, end_day: bool = False) -> str:
    t = time(23, 59, 59) if end_day else time(0, 0, 0)
    dt_local = datetime.combine(d, t).replace(tzinfo=BKK)
    return dt_local.astimezone(UTC).isoformat()


def to_num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


@st.cache_data(ttl=60)
def fetch_table(table_name: str, time_col: str, start_iso: str, end_iso: str):
    result = (
        supabase.table(table_name)
        .select("*")
        .eq("user_id", USER_ID)
        .gte(time_col, start_iso)
        .lte(time_col, end_iso)
        .order(time_col, desc=False)
        .execute()
    )
    return result.data or []


@st.cache_data(ttl=60)
def fetch_goal():
    result = (
        supabase.table("user_goals")
        .select("*")
        .eq("user_id", USER_ID)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else {}


def prep_df(rows, time_col):
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df[time_col] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    df[f"{time_col}_bkk"] = df[time_col].dt.tz_convert(BKK)
    df["date"] = df[f"{time_col}_bkk"].dt.date
    return df


st.title("🏋️ Body Tracker Dashboard")

with st.sidebar:
    st.header("Filter")

    today_bkk = datetime.now(BKK).date()
    start_date = st.date_input("Start date", value=today_bkk - timedelta(days=6))
    end_date = st.date_input("End date", value=today_bkk)

    if start_date > end_date:
        st.error("Start date ต้องไม่เกิน End date")
        st.stop()

    if st.button("Refresh"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"USER_ID: {USER_ID}")


start_iso = local_date_to_utc_iso(start_date)
end_iso = local_date_to_utc_iso(end_date, end_day=True)

food_rows = fetch_table("food_logs", "eaten_at", start_iso, end_iso)
weight_rows = fetch_table("weight_logs", "measured_at", start_iso, end_iso)
workout_rows = fetch_table("workout_logs", "workout_at", start_iso, end_iso)
goal = fetch_goal()

food_df = prep_df(food_rows, "eaten_at")
weight_df = prep_df(weight_rows, "measured_at")
workout_df = prep_df(workout_rows, "workout_at")


for df, cols in [
    (food_df, ["calories", "protein_g", "carbs_g", "fat_g"]),
    (weight_df, ["weight_kg", "bodyfat_pct"]),
    (workout_df, ["duration_min", "calories_burned", "distance_km"]),
]:
    if not df.empty:
        for col in cols:
            if col in df.columns:
                df[col] = df[col].apply(to_num)


total_cal = food_df["calories"].sum() if not food_df.empty and "calories" in food_df else 0
total_protein = food_df["protein_g"].sum() if not food_df.empty and "protein_g" in food_df else 0
total_carbs = food_df["carbs_g"].sum() if not food_df.empty and "carbs_g" in food_df else 0
total_fat = food_df["fat_g"].sum() if not food_df.empty and "fat_g" in food_df else 0

total_workout_min = workout_df["duration_min"].sum() if not workout_df.empty and "duration_min" in workout_df else 0
total_distance = workout_df["distance_km"].sum() if not workout_df.empty and "distance_km" in workout_df else 0

latest_weight = None
if not weight_df.empty and "weight_kg" in weight_df:
    latest_weight = weight_df.iloc[-1]["weight_kg"]


c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Calories", f"{total_cal:,.0f} kcal")
c2.metric("Protein", f"{total_protein:,.0f} g")
c3.metric("Carbs", f"{total_carbs:,.0f} g")
c4.metric("Fat", f"{total_fat:,.0f} g")
c5.metric("Weight", f"{latest_weight:.1f} kg" if latest_weight else "-")


tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 Overview", "🍚 Nutrition", "⚖️ Weight", "🏃 Workout"]
)


with tab1:
    st.subheader("Overview")

    m1, m2 = st.columns(2)
    m1.metric("Workout Duration", f"{total_workout_min:,.0f} min")
    m2.metric("Distance", f"{total_distance:,.1f} km")

    if not food_df.empty:
        daily_food = (
            food_df.groupby("date", as_index=False)
            .agg(
                calories=("calories", "sum"),
                protein_g=("protein_g", "sum"),
                carbs_g=("carbs_g", "sum"),
                fat_g=("fat_g", "sum"),
            )
        )

        fig = px.bar(
            daily_food,
            x="date",
            y="calories",
            title="Calories per day",
            text_auto=True,
        )
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.line(
            daily_food,
            x="date",
            y=["protein_g", "carbs_g", "fat_g"],
            title="Macros per day",
            markers=True,
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("ยังไม่มีข้อมูลอาหารในช่วงวันที่เลือก")


with tab2:
    st.subheader("Nutrition Logs")

    if not food_df.empty:
        cols = [
            "date",
            "meal",
            "food_name",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "note",
        ]
        cols = [c for c in cols if c in food_df.columns]
        st.dataframe(food_df[cols], use_container_width=True)
    else:
        st.info("ยังไม่มี food logs")


with tab3:
    st.subheader("Weight")

    if not weight_df.empty:
        fig = px.line(
            weight_df,
            x="date",
            y="weight_kg",
            title="Weight trend",
            markers=True,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(weight_df, use_container_width=True)
    else:
        st.info("ยังไม่มี weight logs")


with tab4:
    st.subheader("Workout")

    if not workout_df.empty:
        by_type = (
            workout_df.groupby("workout_type", as_index=False)
            .agg(
                count=("id", "count"),
                duration_min=("duration_min", "sum"),
                distance_km=("distance_km", "sum"),
            )
            .sort_values("duration_min", ascending=False)
        )

        fig = px.bar(
            by_type,
            x="workout_type",
            y="duration_min",
            title="Workout duration by type",
            text_auto=True,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(workout_df, use_container_width=True)
    else:
        st.info("ยังไม่มี workout logs")