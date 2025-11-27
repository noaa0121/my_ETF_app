import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="ETF 終極資產試算", page_icon="🏆", layout="wide")

st.title("🏆 ETF 終極資產試算")
st.markdown("""
這個工具集成了 **單筆投入**、**定期定額** 以及 **雙標的 PK 對決** 功能。
利用歷史大數據推算未來，並支援 **下載報表**。
""")

# --- 側邊欄：強大的輸入區 ---
with st.sidebar:
    st.header("1. 設定投資標的")
    ticker1 = st.text_input("選手 A 代號 (需加 .TW)", value="0050.TW")
    
    # 功能 1: 雙強對決
    enable_pk = st.toggle("開啟 PK 模式 (比較第二檔)", value=False)
    ticker2 = ""
    if enable_pk:
        ticker2 = st.text_input("選手 B 代號 (需加 .TW)", value="0056.TW")
    
    st.header("2. 資金投入策略")
    # 功能 2: 單筆 + 定期定額
    initial_lump_sum = st.number_input("單筆投入金額 (一開始的本金)", min_value=0, value=100000, step=10000, help="這是你在第一個月第一天就投入的資金")
    monthly_invest = st.number_input("每月定期定額金額", min_value=0, value=10000, step=1000)
    
    if initial_lump_sum == 0 and monthly_invest == 0:
        st.warning("⚠️ 提醒：單筆投入與每月扣款不能同時為 0")

    st.header("3. 時間與參數")
    future_years = st.slider("預計投資年數", min_value=1, max_value=40, value=10)
    reinvest = st.toggle("股息再投入 (複利)", value=True)
    
    btn_calc = st.button("開始對決 / 分析", type="primary")

# --- 函數：抓取歷史數據並計算指標 ---
def get_historical_metrics(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="max", auto_adjust=False)
        divs = stock.dividends
        
        if hist.empty:
            return None, f"找不到 {ticker_symbol} 的資料"
            
        start_price = hist['Close'].iloc[0]
        end_price = hist['Close'].iloc[-1]
        
        time_diff = (hist.index[-1] - hist.index[0]).days
        years_past = time_diff / 365.25
        
        # 短期數據防呆
        if years_past < 0.01: years_past = 0.01
            
        if start_price > 0:
            price_cagr = (end_price / start_price) ** (1 / years_past) - 1
        else:
            price_cagr = 0
            
        if not divs.empty:
            divs.index = divs.index.tz_localize(None)
            hist.index = hist.index.tz_localize(None)
            yearly_divs = divs.resample('YE').sum()
            yearly_prices = hist['Close'].resample('YE').mean()
            common = yearly_divs.index.intersection(yearly_prices.index)
            if len(common) > 0:
                avg_yield = (yearly_divs[common] / yearly_prices[common]).mean()
            else:
                avg_yield = divs.sum() / hist['Close'].mean() * (1/years_past)
        else:
            avg_yield = 0.0
            
        return {
            "symbol": ticker_symbol,
            "cagr": price_cagr,
            "yield": avg_yield,
            "current_price": end_price,
            "years_data": years_past
        }, None
    except Exception as e:
        return None, str(e)

# --- 函數：推算未來資產 (邏輯升級：加入單筆投入) ---
def calculate_projection(metrics, initial_fund, monthly_amt, years, is_reinvest):
    months = years * 12
    monthly_growth = (1 + metrics['cagr']) ** (1/12) - 1
    monthly_yield = metrics['yield'] / 12
    
    data = []
    
    # 初始狀態
    current_price = metrics['current_price']
    
    # 處理第一筆單筆投入
    total_shares = 0.0
    if initial_fund > 0:
        total_shares = initial_fund / current_price
        
    total_cost = initial_fund
    cash_wallet = 0.0
    total_divs = 0.0
    
    for m in range(1, months + 1):
        # 1. 股價成長
        current_price = current_price * (1 + monthly_growth)
        
        # 2. 定期定額買入
        if monthly_amt > 0:
            new_shares = monthly_amt / current_price
            total_shares += new_shares
            total_cost += monthly_amt
            
        # 3. 處理配息
        market_val = total_shares * current_price
        div_amt = market_val * monthly_yield
        total_divs += div_amt
        
        if is_reinvest:
            total_shares += div_amt / current_price
        else:
            cash_wallet += div_amt
            
        total_asset = (total_shares * current_price) + cash_wallet
        
        data.append({
            "Month": m,
            "Year": m/12,
            "Total Cost": total_cost,
            "Total Assets": total_asset,
            "Accumulated Divs": total_divs,
            "Net Profit": total_asset - total_cost
        })
        
    return pd.DataFrame(data)

# --- 主程式執行區 ---
if btn_calc:
    # 1. 分析選手 A
    with st.spinner(f"正在分析 {ticker1}..."):
        metrics1, err1 = get_historical_metrics(ticker1)
    
    if err1:
        st.error(f"選手 A 錯誤: {err1}")
    else:
        df1 = calculate_projection(metrics1, initial_lump_sum, monthly_invest, future_years, reinvest)
        final1 = df1.iloc[-1]
        roi1 = (final1['Net Profit'] / final1['Total Cost']) * 100

        # 如果有開啟 PK 模式，分析選手 B
        metrics2 = None
        df2 = None
        if enable_pk and ticker2:
            with st.spinner(f"正在分析 {ticker2}..."):
                metrics2, err2 = get_historical_metrics(ticker2)
            if err2:
                st.error(f"選手 B 錯誤: {err2}")
            else:
                df2 = calculate_projection(metrics2, initial_lump_sum, monthly_invest, future_years, reinvest)
        
        # --- 顯示結果介面 ---
        
        # A. 體質比較表
        st.subheader("📊 歷史體質數據 (參考用)")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"### 🔵 {ticker1}")
            st.write(f"年化成長 (CAGR): **{metrics1['cagr']*100:.2f}%**")
            st.write(f"平均殖利率: **{metrics1['yield']*100:.2f}%**")
            st.caption(f"數據長度: {metrics1['years_data']:.1f} 年")
            
        if metrics2:
            with col2:
                st.markdown(f"### 🔴 {ticker2}")
                st.write(f"年化成長 (CAGR): **{metrics2['cagr']*100:.2f}%**")
                st.write(f"平均殖利率: **{metrics2['yield']*100:.2f}%**")
                st.caption(f"數據長度: {metrics2['years_data']:.1f} 年")
        
        st.divider()
        
        # B. 最終結果 PK
        st.subheader(f"🏁 {future_years} 年後資產對決")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("總投入成本", f"${final1['Total Cost']:,.0f}", help="包含單筆投入 + 所有定期定額")
        
        # 顯示選手 A 結果
        c2.metric(f"🔵 {ticker1} 總資產", f"${final1['Total Assets']:,.0f}", delta=f"{roi1:.1f}%")
        
        # 顯示選手 B 結果 (如果有)
        if metrics2 and df2 is not None:
            final2 = df2.iloc[-1]
            roi2 = (final2['Net Profit'] / final2['Total Cost']) * 100
            # 計算勝負差距
            diff = final2['Total Assets'] - final1['Total Assets']
            c3.metric(f"🔴 {ticker2} 總資產", f"${final2['Total Assets']:,.0f}", delta=f"{roi2:.1f}%")
            
            if final1['Total Assets'] > final2['Total Assets']:
                st.success(f"🏆 恭喜！ **{ticker1}** 獲勝，預估多賺 **${abs(diff):,.0f}**")
            else:
                st.error(f"🏆 哎呀！ **{ticker2}** 獲勝，預估多賺 **${abs(diff):,.0f}**")
        else:
            c3.empty()

        # C. 圖表 PK
        st.subheader("📈 資產成長曲線圖")
        chart_data = pd.DataFrame()
        chart_data[f"{ticker1} 總資產"] = df1['Total Assets']
        if metrics2 and df2 is not None:
            chart_data[f"{ticker2} 總資產"] = df2['Total Assets']
        
        # 加入成本線供參考
        chart_data["投入成本"] = df1['Total Cost']
        
        st.line_chart(chart_data, color=["#0000FF", "#FF0000", "#AAAAAA"] if metrics2 else ["#0000FF", "#AAAAAA"])
        
        # D. 下載報表功能 (Feature 3)
        st.divider()
        st.subheader("📥 下載詳細報告")
        
        # 準備下載用的 CSV
        # 為了避免中文亂碼，我們用 utf-8-sig 編碼
        csv = df1.to_csv(index=False).encode('utf-8-sig')
        
        col_dl1, col_dl2 = st.columns(2)
        
        with col_dl1:
            st.download_button(
                label=f"下載 {ticker1} 詳細報表 (CSV)",
                data=csv,
                file_name=f"{ticker1}_report.csv",
                mime='text/csv',
            )
            
        if metrics2 and df2 is not None:
            csv2 = df2.to_csv(index=False).encode('utf-8-sig')
            with col_dl2:
                st.download_button(
                    label=f"下載 {ticker2} 詳細報表 (CSV)",
                    data=csv2,
                    file_name=f"{ticker2}_report.csv",
                    mime='text/csv',
                )

else:
    st.info("👈 請在左側設定參數，體驗完整的資產試算功能！")

