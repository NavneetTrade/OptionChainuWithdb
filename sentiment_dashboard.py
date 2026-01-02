"""
Sentiment Dashboard for Option Chain Analysis
Displays sentiment scores and market insights from database
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone('Asia/Kolkata')


def display_sentiment_dashboard(db_manager):
    """Display sentiment analysis dashboard using database data"""
    try:
        st.header("📊 Market Sentiment Dashboard")
        st.markdown("Real-time sentiment analysis based on option chain data")
        
        # Get available symbols with sentiment data
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT symbol
                    FROM sentiment_scores
                    ORDER BY symbol
                """)
                available_symbols = [row[0] for row in cur.fetchall()]
        
        if not available_symbols:
            st.warning("⚠️ No sentiment data available yet. Background service is collecting data...")
            st.info("💡 Sentiment data will appear here once the background service has processed symbols.")
            return
        
        # Symbol selector
        col1, col2 = st.columns([2, 1])
        with col1:
            selected_symbol = st.selectbox(
                "Select Symbol for Sentiment Analysis",
                available_symbols,
                index=0 if available_symbols else None
            )
        
        with col2:
            time_range = st.selectbox(
                "Time Range",
                ["Last Hour", "Last 4 Hours", "Last 24 Hours", "All Data"],
                index=1
            )
        
        # Get sentiment data for selected symbol
        time_map = {
            "Last Hour": "1 hour",
            "Last 4 Hours": "4 hours",
            "Last 24 Hours": "24 hours",
            "All Data": "7 days"
        }
        
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT timestamp, sentiment_score, sentiment, 
                           confidence, spot_price, pcr_oi, pcr_chgoi, pcr_volume
                    FROM sentiment_scores
                    WHERE symbol = %s
                      AND timestamp > NOW() - INTERVAL '{time_map[time_range]}'
                    ORDER BY timestamp DESC
                """, (selected_symbol,))
                results = cur.fetchall()
        
        if not results:
            st.info(f"No sentiment data for {selected_symbol} in the selected time range")
            return
        
        # Historical trend chart
        if len(results) > 1:
            st.markdown("### Sentiment Trend")
            
            # Prepare data for chart
            df = pd.DataFrame([
                {
                    'timestamp': r[0].astimezone(IST),
                    'sentiment_score': float(r[1]),
                    'sentiment': r[2]
                }
                for r in reversed(results)  # Oldest to newest
            ])
            
            # Create line chart
            fig = go.Figure()
            
            # Add sentiment score line
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['sentiment_score'],
                mode='lines+markers',
                name='Sentiment Score',
                line=dict(color='#1f77b4', width=2),
                marker=dict(size=6)
            ))
            
            # Add threshold lines
            fig.add_hline(y=20, line_dash="dash", line_color="green", 
                         annotation_text="Strong Bullish", annotation_position="right")
            fig.add_hline(y=-20, line_dash="dash", line_color="red",
                         annotation_text="Strong Bearish", annotation_position="right")
            fig.add_hline(y=0, line_dash="dot", line_color="gray",
                         annotation_text="Neutral", annotation_position="right")
            
            fig.update_layout(
                title=f"{selected_symbol} Sentiment Trend",
                xaxis_title="Time",
                yaxis_title="Sentiment Score",
                height=400,
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        # All symbols overview
        st.markdown("---")
        st.subheader("📊 All Symbols Overview")
        
        # Get latest sentiment for all symbols
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ON (symbol) 
                        symbol, sentiment_score, sentiment, timestamp
                    FROM sentiment_scores
                    WHERE timestamp > NOW() - INTERVAL '1 hour'
                    ORDER BY symbol, timestamp DESC
                """)
                all_symbols = cur.fetchall()
        
        if all_symbols:
            # Filter for extreme sentiments
            strong_bullish = []
            strong_bearish = []
            
            for sym, score, sentiment, ts in all_symbols:
                score_val = float(score)
                if score_val > 20:
                    strong_bullish.append((sym, score_val, sentiment))
                elif score_val < -20:
                    strong_bearish.append((sym, score_val, sentiment))
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 🟢 Strong Bullish Signals")
                if strong_bullish:
                    for sym, score, sentiment in sorted(strong_bullish, key=lambda x: x[1], reverse=True):
                        st.success(f"**{sym}**: {score:.2f} ({sentiment})")
                else:
                    st.info("No strong bullish signals")
            
            with col2:
                st.markdown("#### 🔴 Strong Bearish Signals")
                if strong_bearish:
                    for sym, score, sentiment in sorted(strong_bearish, key=lambda x: x[1]):
                        st.error(f"**{sym}**: {score:.2f} ({sentiment})")
                else:
                    st.info("No strong bearish signals")
            
            # Summary statistics
            st.markdown("### Market Summary")
            total_symbols = len(all_symbols)
            bullish_count = sum(1 for _, score, _, _ in all_symbols if float(score) > 0)
            bearish_count = sum(1 for _, score, _, _ in all_symbols if float(score) < 0)
            neutral_count = total_symbols - bullish_count - bearish_count
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Symbols", total_symbols)
            with col2:
                st.metric("Bullish", bullish_count, delta=f"{bullish_count/total_symbols*100:.1f}%" if total_symbols > 0 else "0%")
            with col3:
                st.metric("Bearish", bearish_count, delta=f"{bearish_count/total_symbols*100:.1f}%" if total_symbols > 0 else "0%")
            with col4:
                st.metric("Neutral", neutral_count, delta=f"{neutral_count/total_symbols*100:.1f}%" if total_symbols > 0 else "0%")
        
    except Exception as e:
        st.error(f"Error in sentiment dashboard: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
