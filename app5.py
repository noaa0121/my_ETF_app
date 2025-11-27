import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="ETF 資產試算", page_icon="💎", layout="wide")

st.title("ETF 資產試算")
st.markdown("""
具備 **單筆投入**、**定期定額** 與 **雙標的 PK** 功能。
報表全面升級：包含 **累積股息**、**持有股數** 與 **平均成本 (均價)**。
""")

# --- 側邊欄：輸入區 ---
with st.sidebar:
    st.header("1. 設定投資標的")
    ticker1 = st.text_input("選手 A 代號 (需加 .TW)", value="0050.TW")
    
    # 功能: 雙強對決
    enable_pk = st.toggle("開啟 PK 模式 (比較第二檔)", value=False)
    ticker2 = ""
    if enable_pk:
        ticker2 = st.text_input("選手 B 代號 (需加 .TW)", value="0056.TW")
    
    st.header("2. 資金投入策略")
    initial_lump_sum = st.number_input("單筆投入金額 (初始本金)", min_value=0, value=100000, step=10000)
    monthly_invest = st.number_input("每月定期定額金額", min_value=0, value=10000, step=1000)
    
    if initial_lump_sum == 0 and monthly_invest == 0:
        st.warning("⚠️ 提醒：資金不能全為 0")

    st.header("3. 時間與參數")
    future_years = st.slider("預計投資年數", min_value=1, max_value=40, value=10)
    reinvest = st.toggle("股息再投入(複利)", value=True)
    
    btn_calc = st.button("開始詳細分析", type="primary")

# --- 函數：抓取歷史數據 ---
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

# --- 函數：推算未來資產 (核心修改處) ---
def calculate_projection(metrics, initial_fund, monthly_amt, years, is_reinvest):
    months = years * 12
    monthly_growth = (1 + metrics['cagr']) ** (1/12) - 1
    monthly_yield = metrics['yield'] / 12
    
    data = []
    
    current_price = metrics['current_price']
    total_shares = 0.0
    
    # 處理第一筆單筆投入
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
        total_divs += div_amt # 累計領到的股息總額
        
        if is_reinvest:
            # 股息買入
            shares_from_div = div_amt / current_price
            total_shares += shares_from_div
        else:
            # 存入現金
            cash_wallet += div_amt
            
        # 4. 計算總資產與均價
        total_asset = (total_shares * current_price) + cash_wallet
        
        # 計算均價 (平均成本 = 總投入本金 / 總持有股數)
        # 註：這裡的均價定義為「資金投入的平均成本」，不包含再投入的股息成本(視為零成本取得)，這樣看獲利比較直觀
        if total_shares > 0:
            avg_cost = total_cost / total_shares
        else:
            avg_cost = 0
            
        # 5. 寫入數據 (使用中文欄位，方便 Excel 閱讀)
        data.append({
            "月份": m,
            "年": round(m/12, 2),
            "總投入成本": round(total_cost, 0),
            "累積持有股數": round(total_shares, 2),
            "平均成本(均價)": round(avg_cost, 2),
            "累積領取股息": round(total_divs, 0),
            "預估股價": round(current_price, 2),
            "總資產市值": round(total_asset, 0),
            "損益金額": round(total_asset - total_cost, 0)
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
        roi1 = (final1['損益金額'] / final1['總投入成本']) * 100

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
        
        # A. 體質比較
        st.subheader("📊 歷史體質數據 (參考)")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown(f"### 🔵 {ticker1}")
            st.caption(f"年化成長: {metrics1['cagr']*100:.2f}% | 殖利率: {metrics1['yield']*100:.2f}%")
        if metrics2:
            with col_m2:
                st.markdown(f"### 🔴 {ticker2}")
                st.caption(f"年化成長: {metrics2['cagr']*100:.2f}% | 殖利率: {metrics2['yield']*100:.2f}%")
        
        st.divider()
        
        # B. 詳細結果展示 (重點修改區)
        st.subheader(f"🏁 {future_years} 年後資產總覽")
        
        # 顯示總成本 (大家都一樣)
        st.metric("💰 總投入成本", f"${final1['總投入成本']:,.0f}")
        
        # 選手 A 詳細數據
        st.markdown(f"#### 🔵 {ticker1} 最終成績單")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("總資產", f"${final1['總資產市值']:,.0f}", delta=f"{roi1:.1f}%")
        c2.metric("累積領取股息", f"${final1['累積領取股息']:,.0f}")
        c3.metric("持有股數", f"{final1['累積持有股數']:,.0f} 股")
        c4.metric("平均均價", f"${final1['平均成本(均價)']:,.2f}", delta=f"現價 ${final1['預估股價']:,.2f}")

        # 選手 B 詳細數據 (如果有)
        if metrics2 and df2 is not None:
            final2 = df2.iloc[-1]
            roi2 = (final2['損益金額'] / final2['總投入成本']) * 100
            st.markdown("---")
            st.markdown(f"#### 🔴 {ticker2} 最終成績單")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("總資產", f"${final2['總資產市值']:,.0f}", delta=f"{roi2:.1f}%")
            d2.metric("累積領取股息", f"${final2['累積領取股息']:,.0f}")
            d3.metric("持有股數", f"{final2['累積持有股數']:,.0f} 股")
            d4.metric("平均均價", f"${final2['平均成本(均價)']:,.2f}", delta=f"現價 ${final2['預估股價']:,.2f}")
            
            # 勝負判定
            diff = final1['總資產市值'] - final2['總資產市值']
            if diff > 0:
                st.success(f"🏆 結論：**{ticker1}** 獲勝！ 預估總資產多出 **${abs(diff):,.0f}**")
            else:
                st.error(f"🏆 結論：**{ticker2}** 獲勝！ 預估總資產多出 **${abs(diff):,.0f}**")

        # C. 圖表 PK
        st.divider()
        st.subheader("📈 資產成長曲線")
        chart_data = pd.DataFrame()
        chart_data[f"{ticker1} 總資產"] = df1['總資產市值']
        if metrics2 and df2 is not None:
            chart_data[f"{ticker2} 總資產"] = df2['總資產市值']
        chart_data["投入成本"] = df1['總投入成本']
        
        st.line_chart(chart_data, color=["#0000FF", "#FF0000", "#AAAAAA"] if metrics2 else ["#0000FF", "#AAAAAA"])
        
        # D. 下載報表 (含詳細欄位)
        st.divider()
        st.subheader("📥 下載詳細報告 (含均價與股息)")
        
        # CSV 1
        csv1 = df1.to_csv(index=False).encode('utf-8-sig')
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label=f"下載 {ticker1} 完整報表 (CSV)",
                data=csv1,
                file_name=f"{ticker1}_report.csv",
                mime='text/csv',
            )
        
        # CSV 2
        if metrics2 and df2 is not None:
            csv2 = df2.to_csv(index=False).encode('utf-8-sig')
            with col_dl2:
                st.download_button(
                    label=f"下載 {ticker2} 完整報表 (CSV)",
                    data=csv2,
                    file_name=f"{ticker2}_report.csv",
                    mime='text/csv',
                )

else:
    st.info("👈 請在左側輸入代號與金額，開始你的財富試算！")
