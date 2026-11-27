from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from indicators.technical import ema


def build_signal_candlestick_chart(
    df: pd.DataFrame,
    ticker: str,
    entry: float,
    stop: float,
    target1: float,
    target2: float,
    is_intraday: bool = False,
) -> go.Figure:
    sub = df.tail(80).copy()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.74, 0.26])

    fig.add_trace(
        go.Candlestick(
            x=sub.index,
            open=sub["Open"],
            high=sub["High"],
            low=sub["Low"],
            close=sub["Close"],
            name=ticker,
        ),
        row=1,
        col=1,
    )

    if is_intraday:
        sub["day"] = sub.index.date
        tp = (sub["High"] + sub["Low"] + sub["Close"]) / 3
        vwap = (tp * sub["Volume"]).groupby(sub["day"]).cumsum() / sub.groupby("day")["Volume"].cumsum()
        fig.add_trace(go.Scatter(x=sub.index, y=vwap, mode="lines", name="VWAP", line=dict(color="#8b5cf6", width=1.6)), row=1, col=1)
        fig.add_trace(go.Scatter(x=sub.index, y=ema(sub["Close"], 20), mode="lines", name="EMA 20", line=dict(color="#0284c7", width=1.4)), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=sub.index, y=ema(sub["Close"], 20), mode="lines", name="EMA 20", line=dict(color="#0284c7", width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=sub.index, y=ema(sub["Close"], 50), mode="lines", name="EMA 50", line=dict(color="#f59e0b", width=1.5)), row=1, col=1)

    for lvl, lbl, col in [
        (entry, f"Giriş: {entry:.2f}", "#2563eb"),
        (stop, f"Stop: {stop:.2f}", "#dc2626"),
        (target1, f"Hedef 1: {target1:.2f}", "#16a34a"),
        (target2, f"Hedef 2: {target2:.2f}", "#059669"),
    ]:
        fig.add_hline(y=lvl, line_dash="dash", line_color=col, annotation_text=lbl, annotation_position="top left", row=1, col=1)

    vol_colors = ["#16a34a" if c >= o else "#dc2626" for c, o in zip(sub["Close"], sub["Open"])]
    fig.add_trace(go.Bar(x=sub.index, y=sub["Volume"], name="Hacim", marker_color=vol_colors, opacity=0.7), row=2, col=1)

    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=28, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig
