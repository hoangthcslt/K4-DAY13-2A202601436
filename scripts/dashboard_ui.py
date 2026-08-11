import json
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

st.set_page_config(page_title="Day 13 AI Observability", layout="wide")
st.title("Day 13 AI Observability Dashboard")
st.write("Cửa sổ thời gian: 60 phút gần nhất. Tự động refresh mỗi 30s.")

@st.cache_data(ttl=30)
def load_data():
    logs = []
    with open("data/logs.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                logs.append(json.loads(line))
    
    if not logs:
        return pd.DataFrame()
    
    df = pd.DataFrame(logs)
    df["ts"] = pd.to_datetime(df["ts"])
    
    # Filter last 60 minutes
    now = df["ts"].max()
    df = df[df["ts"] >= now - timedelta(minutes=60)]
    return df

df = load_data()

if df.empty:
    st.warning("Không có dữ liệu log trong 60 phút qua.")
else:
    # 1. Latency (P50, P95, P99)
    st.subheader("1. Latency percentiles (ms)")
    df_resp = df[df["event"] == "response_sent"].copy()
    if not df_resp.empty:
        p50 = df_resp["latency_ms"].quantile(0.50)
        p95 = df_resp["latency_ms"].quantile(0.95)
        p99 = df_resp["latency_ms"].quantile(0.99)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("P50", f"{p50:.1f} ms")
        col2.metric("P95", f"{p95:.1f} ms", delta=f"{p95-3000:.1f} ms từ SLO 3000" if p95 > 3000 else "Đạt chuẩn", delta_color="inverse")
        col3.metric("P99", f"{p99:.1f} ms")
        col4.metric("Threshold (P95)", "<= 3000 ms")
        st.line_chart(df_resp.set_index("ts")["latency_ms"])
    else:
        st.info("Chưa có event response_sent")

    st.divider()

    # 2. Traffic
    st.subheader("2. Request traffic (requests_per_minute)")
    df_req = df[df["event"] == "request_received"].copy()
    if not df_req.empty:
        df_req_count = df_req.set_index("ts").resample("1min").size()
        current_rate = df_req_count.iloc[-1] if not df_req_count.empty else 0
        total_count = len(df_req)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total requests (60m)", total_count)
        col2.metric("Rate per minute (hiện tại)", current_rate, delta=">= 1 (Threshold)" if current_rate >= 1 else "Dưới ngưỡng")
        col3.metric("Threshold (Rate)", ">= 1 req/min")
        st.bar_chart(df_req_count)
    else:
        st.info("Chưa có event request_received")

    st.divider()

    # 3. Errors
    st.subheader("3. Error rate and breakdown (%)")
    failed = len(df[df["event"] == "request_failed"])
    received = len(df_req)
    error_rate = (failed / received * 100) if received > 0 else 0
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Error Rate", f"{error_rate:.2f} %", delta=f"{error_rate-2:.2f} %" if error_rate > 2 else "Đạt chuẩn", delta_color="inverse")
    col2.metric("Total Errors", failed)
    col3.metric("Threshold", "<= 2 %")
    
    if failed > 0:
        error_types = df[df["event"] == "request_failed"]["error_type"].value_counts()
        st.bar_chart(error_types)

    st.divider()

    # 4. Cost
    st.subheader("4. Cost over time (USD)")
    if not df_resp.empty and "cost_usd" in df_resp.columns:
        total_cost = df_resp["cost_usd"].sum()
        cost_per_min = df_resp.set_index("ts")["cost_usd"].resample("1min").sum()
        
        col1, col2 = st.columns(2)
        col1.metric("Total Cost", f"${total_cost:.4f}", delta="Cảnh báo > $2.5" if total_cost > 2.5 else "Đạt chuẩn", delta_color="inverse")
        col2.metric("Threshold", "<= $2.5")
        st.line_chart(cost_per_min)
    
    st.divider()

    # 5. Tokens
    st.subheader("5. Input and output tokens")
    if not df_resp.empty and "tokens_in" in df_resp.columns and "tokens_out" in df_resp.columns:
        total_in = df_resp["tokens_in"].sum()
        total_out = df_resp["tokens_out"].sum()
        total_tokens = total_in + total_out
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Tokens", total_tokens, delta="Vượt SLO 50,000" if total_tokens > 50000 else "Đạt chuẩn", delta_color="inverse")
        col2.metric("Tokens In", total_in)
        col3.metric("Tokens Out", total_out)
        col4.metric("Threshold", "<= 50000 tokens")

    st.divider()

    # 6. Quality Proxy
    st.subheader("6. Quality proxy (score_0_to_1)")
    if not df_resp.empty and "quality_score" in df_resp.columns:
        mean_quality = df_resp["quality_score"].mean()
        
        col1, col2 = st.columns(2)
        col1.metric("Mean Quality Score", f"{mean_quality:.2f}", delta=f"{mean_quality-0.75:.2f}" if mean_quality < 0.75 else "Đạt chuẩn")
        col2.metric("Threshold", ">= 0.75")
        st.line_chart(df_resp.set_index("ts")["quality_score"])
