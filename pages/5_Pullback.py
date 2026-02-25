"""
🎯 寻星二波雷达 V1 - 中线价值与缩量回调模型
================================================================
"""
import streamlit as st
import pandas as pd
import numpy as np
import tushare as ts
from datetime import datetime, timedelta
import sys, os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_fetcher import _get_tushare_pro, _last_trade_date

st.set_page_config(page_title="二波雷达", page_icon="🎯", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("请先登录")
    st.page_link("app.py", label="🔐 返回登录", icon="🏠")
    st.stop()

st.title("🎯 寻星中线配置雷达 — 强势股二波博弈")
st.caption("策略锚定: [流通市值 20-100亿] + [科技/AI/国资属性] + [PE>0] + [拉升>40%后缩量回调50%]")
st.divider()

# ============================================================
# 参数配置面板
# ============================================================
col_p1, col_p2, col_p3, col_p4 = st.columns(4)
with col_p1:
    target_concepts = st.multiselect("概念板块过滤", 
        ["人工智能", "算力", "半导体", "IT设备", "通信设备", "软件服务", "人形机器人", "元器件"],
        default=["人工智能", "算力", "半导体", "通信设备"])
with col_p2:
    surge_threshold = st.slider("第一波拉升幅度下限 (%)", 20, 80, 40, step=5)
with col_p3:
    vol_shrink = st.slider("回调期量能萎缩率下限 (%)", 20, 60, 45, help="回调期日均量不得超过拉升期的该百分比，越小要求缩量越极端")
with col_p4:
    st.write("")
    run_btn = st.button("🚀 启动中线雷达扫描", type="primary", use_container_width=True)

if not run_btn:
    st.info("💡 架构师提示：系统将首先进行 PE 与市值的基本面过滤，随后执行极其严苛的 K 线形态匹配。")
    st.stop()

pro = _get_tushare_pro()
if not pro:
    st.error("⚠️ 本策略必须依赖 Tushare PRO，请检查配置。")
    st.stop()

# ============================================================
# 核心引擎计算
# ============================================================
progress = st.progress(0, "Stage 1/3: 获取全市场基础数据与估值...")

try:
    # 1. 基本面滤网 (The Fundamental Funnel)
    today = _last_trade_date()
    
    # 获取基础信息
    df_basic = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,industry')
    df_basic = df_basic[~df_basic['name'].str.contains('ST|退')]
    
    # 获取估值与市值
    df_daily = pro.daily_basic(trade_date=today, fields='ts_code,circ_mv,pe_ttm,pb')
    if df_daily is None or df_daily.empty:
        df_daily = pro.daily_basic(trade_date=_last_trade_date(1), fields='ts_code,circ_mv,pe_ttm,pb')

    progress.progress(20, "Stage 1/3: 执行矩阵交集过滤 (市值+盈利+行业)...")
    
    df_merged = pd.merge(df_basic, df_daily, on='ts_code')
    
    # Tushare circ_mv 单位为万元。20亿 = 200,000；100亿 = 1,000,000
    cond_mv = (df_merged['circ_mv'] >= 200000) & (df_merged['circ_mv'] <= 1000000)
    cond_pe = (df_merged['pe_ttm'] > 0) & (df_merged['pe_ttm'] < 80) # 中线必须有基本面支撑
    cond_ind = df_merged['industry'].isin(target_concepts)
    
    df_universe = df_merged[cond_mv & cond_pe & cond_ind].copy()
    total_candidates = len(df_universe)
    
    progress.progress(40, f"Stage 2/3: 基本面过滤完毕，剩余 {total_candidates} 只标的。准备进入形态识别引擎...")
    
    if total_candidates == 0:
        st.warning("当前市场环境下，没有符合[中小盘+目标概念+PE盈利]基本面要求的股票。")
        st.stop()
        
    # 2. 形态识别滤网 (The Technical Funnel)
    # 计算时间窗口：过去 80 个交易日
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=120)).strftime('%Y%m%d') 
    
    signals = []
    
    # 遍历计算
    for idx, row in df_universe.iterrows():
        ts_code = row['ts_code']
        name = row['name']
        
        # 实时更新进度条
        current_prog = 40 + int(60 * (idx / total_candidates))
        progress.progress(current_prog, f"Stage 3/3: 正在核算量价形态 - {name} ({idx+1}/{total_candidates})")
        
        # 【架构师底线】：必须强制使用前复权 pro_bar
        # 为防止 Tushare 限流，插入极短延时
        time.sleep(0.05) 
        df_k = ts.pro_bar(ts_code=ts_code, api=pro, adj='qfq', start_date=start_date, end_date=end_date)
        
        if df_k is None or len(df_k) < 40:
            continue
            
        df_k = df_k.sort_values('trade_date').reset_index(drop=True)
        
        # --- 寻星核心形态算法 ---
        # A. 寻找拉升浪的峰值 (Peak) 和 谷值 (Base)
        search_window = df_k.iloc[:-5] # 留出最近5天作为回调验证期
        peak_idx = search_window['high'].idxmax()
        peak_price = search_window.loc[peak_idx, 'high']
        
        # 如果波峰出现在太久之前（比如60个交易日前），判定为过气题材，忽略
        if len(df_k) - peak_idx > 30:
            continue
            
        base_window = search_window.iloc[:peak_idx]
        if len(base_window) < 5: continue
        base_idx = base_window['low'].idxmin()
        base_price = base_window.loc[base_idx, 'low']
        
        # B. 验证拉升幅度
        surge = (peak_price - base_price) / base_price
        if surge < (surge_threshold / 100):
            continue
            
        # C. 验证 50% 黄金坑深度
        current_price = df_k.iloc[-1]['close']
        target_price = peak_price - (peak_price - base_price) * 0.5
        tolerance = target_price * 0.12 # 允许支撑位上下 12% 的误差宽幅
        
        if not (target_price - tolerance <= current_price <= target_price + tolerance):
            continue
            
        # D. 致命校验：缩量断层 (主力是否出逃)
        impulse_vol = df_k.iloc[base_idx:peak_idx+1]['vol'].mean()
        pullback_vol = df_k.iloc[peak_idx+1:]['vol'].mean()
        
        shrink_ratio = pullback_vol / impulse_vol
        if shrink_ratio > (vol_shrink / 100):
            continue # 放量下跌，大概率A杀，直接舍弃
            
        # 符合所有条件，装载信号
        signals.append({
            "股票代码": ts_code,
            "名称": name,
            "所属行业": row['industry'],
            "流通市值(亿)": round(row['circ_mv'] / 10000, 1),
            "PE(TTM)": round(row['pe_ttm'], 1),
            "首波涨幅": f"{surge*100:.1f}%",
            "当前价格": current_price,
            "50%支撑价": round(target_price, 2),
            "回调缩量比": f"{shrink_ratio*100:.1f}%"
        })

    progress.progress(100, "✅ 扫描完成！")
    
    # 3. 结果渲染
    if not signals:
        st.warning("⚠️ 扫描结束。今日全市场无一只股票符合 [基本面安全垫 + 极度缩量回调] 的双重过滤。请保持耐心空仓。")
    else:
        df_result = pd.DataFrame(signals)
        st.success(f"🎯 狩猎成功：发现 {len(df_result)} 只符合寻星标准的极光标的！")
        st.dataframe(df_result, use_container_width=True)
        
        # 风险提示
        st.markdown("""
        ### 🛡️ 寻星 CIO 中线操作指引
        1. **买入纪律**：股价需在【50%支撑价】附近企稳（出现长下影线或小阳线）方可建仓，严禁在加速大阴线中左侧接飞刀。
        2. **止损纪律**：若收盘价有效跌破【50%支撑价】的 **8%**，意味着形态彻底破位（主力已在高位派发完毕），必须无条件止损。
        """)

except Exception as e:
    st.error(f"系统运行异常，请检查网络或 Tushare 接口配额: {str(e)}")