import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="ETF 未來資產詳細試算 (解除限制版)", page_icon="🚀", layout="wide")

st.title("🚀 ETF 未來資產詳細預測")
st.markdown("""
本工具基於標的 **「上市至今」** 的歷史平均表現，推算未來的資產變化。
已解除上市時間限制，**新上市 ETF 亦可計算** (但請注意短期數據波動較大)。
""")

# --- 側邊欄：使用者輸入 ---
with st.sidebar:
    st.header("1. 設定標的與參數")
    ticker = st.text_input("輸入台股代號 (需加 .TW)", value="00940.TW") # 換個新一點的預設值
    
    st.header("2. 未來投資計畫")
    monthly_invest = st.number_input("每月定期定額金額 (TWD)", min_value=1000, value=10000, step=1000)
    future_years = st.slider("預計持續投資年數", min_value=1, max_value=40, value=10)
    
    st.header("3. 策略設定")
    reinvest = st.toggle("假設股息再投入 (複利)", value=True)
    st.caption("開啟：股息會自動買入更多股數 (複利)。\n關閉：股息以現金保留。")
    
    btn_calc = st.button("開始詳細分析", type="primary")

# --- 核心函數：計算歷史指標 (已修改：解除 1 年限制) ---
def get_historical_metrics(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        # 抓取最大範圍歷史資料
        hist = stock.history(period="max", auto_adjust=False)
        divs = stock.dividends
        
        if hist.empty:
            return None, "錯誤：找不到歷史股價資料，請確認代號是否正確。"
            
        # 1. 計算股價年化報酬率 (CAGR)
        start_price = hist['Close'].iloc[0]
        end_price = hist['Close'].iloc[-1]
        
        # 計算總天數
        time_diff = (hist.index[-1] - hist.index[0]).days
        years_past = time_diff / 365.25
        
        # --- 修改重點開始 ---
        # 移除原本 "if years_past < 1: return error" 的限制
        # 改為防呆機制，避免剛上市第一天 years_past 為 0 造成除法錯誤
        is_short_term = False
        if years_past < 0.01: 
            # 如果上市不到 3 天，給予極小值避免報錯
            years_past = 0.01 
            is_short_term = True
        elif years_past < 1:
            is_short_term = True
        # --- 修改重點結束 ---

        # CAGR 公式
        # 注意：如果上市時間很短且漲幅很大，這裡算出來的 % 數會非常驚人 (年化效應)
        if start_price > 0:
            price_cagr = (end_price / start_price) ** (1 / years_past) - 1
        else:
            price_cagr = 0
        
        # 2. 計算平均殖利率
        if not divs.empty:
            divs.index = divs.index.tz_localize(None)
            hist.index = hist.index.tz_localize(None)
            
            # 使用 'YE' 避免警告
            yearly_divs = divs.resample('YE').sum()
            yearly_prices = hist['Close'].resample('YE').mean()
            
            common_years = yearly_divs.index.intersection(yearly_prices.index)
            if len(common_years) > 0:
                yearly_yields = yearly_divs[common_years] / yearly_prices[common_years]
                avg_yield = yearly_yields.mean()
            else:
                # 如果資料不滿一年，無法 resample('YE')，我們直接用 總配息 / 平均股價 來估算
                total_divs_period = divs.sum()
                avg_price_period = hist['Close'].mean()
                yield_period = total_divs_period / avg_price_period
                # 將期間殖利率換算成年化 (簡單估算)
                avg_yield = yield_period * (1 / years_past)
        else:
            avg_yield = 0.0
            
        return {
            "cagr": price_cagr,
            "yield": avg_yield,
            "years_data": years_past,
            "current_price": end_price,
            "start_date": hist.index[0].date(),
            "end_date": hist.index[-1].date(),
            "is_short_term": is_short_term # 回傳是否為短期資料的標記
        }, None
        
    except Exception as e:
        return None, f"發生錯誤: {str(e)}"

# --- 核心函數：推算未來資產 ---
def project_future_wealth(start_price, monthly_amt, years, cagr, div_yield, is_reinvest):
    months = years * 12
    monthly_price_growth = (1 + cagr) ** (1/12) - 1
    monthly_yield_rate = div_yield / 12
    
    data = []
    current_sim_price = start_price
    total_shares = 0.0
    total_cost = 0.0
    total_dividends_received = 0.0
    cash_wallet = 0.0
    
    for m in range(1, months + 1):
        current_sim_price = current_sim_price * (1 + monthly_price_growth)
        shares_bought = monthly_amt / current_sim_price
        total_shares += shares_bought
        total_cost += monthly_amt
        
        current_market_val = total_shares * current_sim_price
        dividend_amt = current_market_val * monthly_yield_rate
        total_dividends_received += dividend_amt
        
        if is_reinvest:
            shares_from_div = dividend_amt / current_sim_price
            total_shares += shares_from_div
        else:
            cash_wallet += dividend_amt
        
        stock_assets = total_shares * current_sim_price
        total_assets = stock_assets + cash_wallet
        
        if total_shares > 0:
            avg_cost = total_cost / total_shares
        else:
            avg_cost = 0
            
        data.append({
            "Month": m,
            "Total Cost": total_cost,
            "Total Assets": total_assets,
            "Total Dividends": total_dividends_received,
            "Total Shares": total_shares,
            "Sim Price": current_sim_price,
            "Avg Cost": avg_cost
        })
        
    return pd.DataFrame(data)

# --- 主程式 ---
if btn_calc:
    with st.spinner(f"正在分析 {ticker} 歷史數據..."):
        metrics, error = get_historical_metrics(ticker)
        
    if error:
        st.error(error)
    else:
        # 1. 歷史數據看板
        st.subheader(f"📊 {ticker} 歷史體質")
        st.caption(f"數據來源：{metrics['start_date']} ~ {metrics['end_date']} (共 {metrics['years_data']:.2f} 年)")
        
        # 如果是短期數據，顯示警告
        if metrics['is_short_term']:
            st.warning("⚠️ 注意：此標的上市未滿一年。年化報酬率 (CAGR) 是根據極短期的漲跌幅直接推算，可能會過度放大（例如將一個月的漲幅乘以 12 倍），請謹慎參考預測結果。")

        m1, m2, m3 = st.columns(3)
        m1.metric("年化報酬 (CAGR)", f"{metrics['cagr']*100:.2f}%")
        m2.metric("年化殖利率 (Yield)", f"{metrics['yield']*100:.2f}%")
        m3.metric("最新股價", f"${metrics['current_price']:.2f}")
        
        st.markdown("---")
        
        # 2. 未來推算
        st.subheader(f"🔮 {future_years} 年後資產預測")
        
        df = project_future_wealth(
            metrics['current_price'],
            monthly_invest,
            future_years,
            metrics['cagr'],
            metrics['yield'],
            reinvest
        )
        
        last_row = df.iloc[-1]
        final_assets = last_row['Total Assets']
        profit = final_assets - last_row['Total Cost']
        roi = (profit / last_row['Total Cost']) * 100
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 預估總資產", f"${final_assets:,.0f}", delta=f"獲利 ${profit:,.0f}")
        c2.metric("💸 總投入本金", f"${last_row['Total Cost']:,.0f}")
        c3.metric("📈 總報酬率", f"{roi:.2f}%")
        
        st.markdown("#### 📌 詳細持倉指標")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("🧾 累積總領股息", f"${last_row['Total Dividends']:,.0f}")
        d2.metric("📦 累積持有股數", f"{last_row['Total Shares']:.0f} 股")
        d3.metric("⚖️ 平均購入均價", f"${last_row['Avg Cost']:.2f}")
        d4.metric("🏁 預估結算股價", f"${last_row['Sim Price']:.2f}")

        st.markdown("---")
        st.subheader("📈 資產成長預測圖")
        st.line_chart(df[['Total Assets', 'Total Cost', 'Total Dividends']], color=["#00FF00", "#FF0000", "#0000FF"])
        
        with st.expander("查看詳細月度報表"):
            st.dataframe(df.style.format("{:,.2f}"))

else:
    st.info("👈 請輸入代號並點擊按鈕開始試算")