from __future__ import annotations
import html
from typing import List
import pandas as pd
import streamlit as st
from config import TZ
from data.sources import SourceHealth
from exceptions import ValidationError
from storage.repository import add_trade
from strategy.analyzer import get_calibrated_label
from ui.charts import build_signal_candlestick_chart


def tl(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render_legal_disclaimer() -> None:
    st.warning(
        "⚖️ **Yasal Uyarı ve Sorumluluk Reddi (SPK Bildirimi):** Bu yazılım yalnızca **eğitim, istatistiksel analiz ve karar destek** "
        "amacıyla geliştirilmiştir. Üretilen teknik skorlar, destek/direnç seviyeleri ve pozisyon büyüklüğü hesaplamaları "
        "**yatırım danışmanlığı veya al-sat-tut tavsiyesi niteliği taşımaz**. Yatırım kararlarınızı kendi risk profilinize göre "
        "veriniz. Uygulamayı üçüncü kişilere veya abonelere açmayı planlıyorsanız **6362 sayılı Sermaye Piyasası Kanunu (SPK)** "
        "kapsamında yetkili hukuk danışmanından görüş almanız zorunludur."
    )


def render_source_health_panel(health_items: List[SourceHealth], scan_funnel: dict) -> None:
    with st.expander("🩺 Veri Kaynağı Sağlığı, Veri Yaşı ve Tarama Kapsamı"):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Toplam Evren", f"{scan_funnel.get('universe', 0)} hisse")
        c2.metric("Verisi Gelen", f"{scan_funnel.get('loaded', 0)} hisse")
        c3.metric("Ön Filtre Geçen", f"{scan_funnel.get('passed_pre', 0)} hisse")
        c4.metric("Ağır Analiz / Kesilen", f"{scan_funnel.get('analyzed', 0)} / {scan_funnel.get('truncated', 0)}")

        rows = []
        for h in health_items:
            rows.append({
                "Kaynak": h.name,
                "Durum": "✅ Çalışıyor" if h.ok else "❌ Hata / Kapalı",
                "Gelen Hisse": h.count,
                "Son Mum Zamanı": h.last_bar_ts or "-",
                "Veri Yaşı (dk)": h.age_minutes if h.age_minutes is not None else "-",
                "Not / Hata": h.error or "Sorunsuz",
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _cb_apply_live(ticker: str, inp_key: str):
    val = float(st.session_state.get(inp_key, 0.0))
    live_dict = st.session_state.setdefault("live_prices", {})
    live_times = st.session_state.setdefault("live_times", {})
    if val > 0:
        live_dict[ticker] = val
        live_times[ticker] = pd.Timestamp.now(TZ).strftime("%H:%M")
    else:
        live_dict.pop(ticker, None)
        live_times.pop(ticker, None)


def _cb_clear_live(ticker: str, inp_key: str):
    st.session_state.setdefault("live_prices", {}).pop(ticker, None)
    st.session_state.setdefault("live_times", {}).pop(ticker, None)
    st.session_state[inp_key] = 0.0


def _cb_track_trade(mode_name: str, ticker: str, entry: float, stop: float, t1: float, t2: float, lot: int):
    try:
        add_trade(mode_name, ticker, entry, stop, t1, t2, lot)
        st.session_state["last_toast"] = f"✅ {ticker} ({tl(entry)} TL • {lot} lot) işlem günlüğüne eklendi!"
    except ValidationError as exc:
        st.session_state["last_toast"] = f"⚠️ {exc}"


def render_signal_card(r: dict, info: dict, frows: list, mode_name: str, chart_df: pd.DataFrame | None = None, key_prefix: str = "opp") -> None:
    label, col = get_calibrated_label(r["Genel"])
    is_swing = "Birkaç Günlük" in mode_name

    safe_ticker = html.escape(str(r["Hisse"]))
    raw_sector = info.get("sector") or info.get("industry") or ("Gün İçi Karar Destek" if not is_swing else "Çok Günlük Trend")
    safe_sector = html.escape(str(raw_sector))
    safe_src = html.escape(str(r.get("PriceSource", "Piyasa Verisi")))
    safe_upd = html.escape(str(r.get("UpdatedAt", "-")))
    safe_note = html.escape(str(r.get("PlanNote", "")))

    is_live = r.get("IsLive", False)
    card_cls = "card-live" if is_live else "card"
    badge = (
        f'<span class="live-badge">⚡ MANUEL FİYAT • {safe_upd}</span>'
        if is_live
        else f'<span class="src-badge">📡 {safe_src} • 🕒 {safe_upd}</span>'
    )

    card_html = (
        f'<div class="{card_cls}"><div class="top"><div><div class="tk">{safe_ticker}{badge}</div>'
        f'<div class="sub">{safe_sector} • Referans Fiyat: <b>{tl(r["Fiyat"])} TL</b> (%{r["Değişim"]:+.1f}) • Veri Zamanı: <b>{safe_upd}</b></div></div>'
        f'<div class="pill" style="background:{col}">{html.escape(label)} • {r["Genel"]:.0f}/100</div></div>'
        f'<div class="summary-box"><small>📐 <b>Plan Hesaplama Mantığı (BIST Adım Yuvarlamalı):</b> {safe_note}</small></div>'
        f'<div class="grid">'
        f'<div class="box"><small>Referans Seviye</small><b>{tl(r["Fiyat"])} TL</b></div>'
        f'<div class="box"><small>Zarar Kes (Stop)</small><b>{tl(r["Stop"])} TL</b></div>'
        f'<div class="box"><small>1. Hedef Seviye</small><b>{tl(r["Hedef1"])} TL</b></div>'
        f'<div class="box"><small>2. Hedef Seviye</small><b>{tl(r["Hedef2"])} TL</b></div></div></div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)

    live_dict = st.session_state.setdefault("live_prices", {})
    inp_key = f"inp_live_{key_prefix}_{mode_name}_{r['Hisse']}"
    if inp_key not in st.session_state:
        st.session_state[inp_key] = float(live_dict.get(r["Hisse"], 0.0))

    cols = st.columns([2.0, 1.35, 0.95, 1.25]) if is_live else st.columns([2.2, 1.4, 1.3])
    with cols[0]:
        st.number_input(
            f"{r['Hisse']} Manuel Fiyat",
            min_value=0.0, step=0.05, format="%.2f", key=inp_key, label_visibility="collapsed"
        )
    with cols[1]:
        st.button("⚡ Fiyatı Uygula", key=f"btn_live_{key_prefix}_{mode_name}_{r['Hisse']}", use_container_width=True, on_click=_cb_apply_live, args=(r["Hisse"], inp_key))
    if is_live:
        with cols[2]:
            st.button("🧹 Temizle", key=f"btn_clr_{key_prefix}_{mode_name}_{r['Hisse']}", use_container_width=True, on_click=_cb_clear_live, args=(r["Hisse"], inp_key))
        track_col = cols[3]
    else:
        track_col = cols[2]

    pos = r["Pos"]
    with track_col:
        st.button(
            "📝 Günlüğe Ekle",
            key=f"log_{key_prefix}_{mode_name}_{r['Hisse']}",
            use_container_width=True,
            type="primary",
            disabled=not pos.affordable,
            on_click=_cb_track_trade,
            args=(mode_name, r["Hisse"], r["Fiyat"], r["Stop"], r["Hedef1"], r["Hedef2"], pos.lot),
        )

    if not pos.affordable:
        st.error(f"🚫 **Pozisyon Boyutu Uyarısı:** {pos.reason}")
    else:
        st.info(
            f"📌 **Risk Bazlı Pozisyon Hesabı:** **{pos.lot} lot** (Maliyet + Komisyon/BSMV: **~{tl(pos.total_cost)} TL**) • "
            f"Stop Riski (Komisyon+Kayma Dahil): **{tl(pos.expected_stop_loss_tl)} TL** • "
            f"1. Hedefte Net Beklenti: **{tl(pos.expected_t1_gain_tl)} TL**."
        )

    with st.expander(f"📊 {r['Hisse']} Etkileşimli Grafik, Teknik & Bilanço Detayları"):
        if chart_df is not None and not chart_df.empty:
            fig = build_signal_candlestick_chart(
                chart_df, r["Hisse"], r["Fiyat"], r["Stop"], r["Hedef1"], r["Hedef2"], is_intraday=not is_swing
            )
            st.plotly_chart(fig, use_container_width=True)

        st.caption(f"🔎 **Veri Dayanağı:** Fiyat Kaynağı = `{r.get('PriceSource')}` | Bilanço Kaynağı = `{info.get('_source', 'Yok')}` | Güncelleme = `{r.get('UpdatedAt')}`")
        for lbl, ok in r["Kontroller"]:
            st.write(("✅ " if ok else "❌ ") + lbl)
        if is_swing and frows:
            st.markdown("**Sektör & Enflasyon Uyumlu Bilanço Kontrolleri:**")
            for n, v, rule, good in frows:
                st.write(f"{'✅' if good else '⬜'} {n}: **{v}** (Eşik: {rule})")
