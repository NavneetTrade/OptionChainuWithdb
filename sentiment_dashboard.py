"""
Sentiment Dashboard - Shows all symbols with extreme sentiment scores
Calculates sentiment using same ITM filtering as Option Chain Analysis
"""

import streamlit as st
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime
import pytz

from database import TimescaleDBManager
from optionchain import (
    format_ist_time, 
    get_fo_instruments,
    process_option_chain_data,
    calculate_bucket_summaries,
    calculate_comprehensive_pcr,
    calculate_comprehensive_sentiment_score
)

IST = pytz.timezone('Asia/Kolkata')


def get_all_symbols_sentiment(db_manager: TimescaleDBManager, min_score: float = 20, max_score: float = -20) -> List[Dict]:
    """
    Get all symbols with sentiment scores outside the range [max_score, min_score]
    SIMPLY fetches from database - no calculation, no complex filtering.
    Uses the same data source as Option Chain Analysis.
    
    Args:
        db_manager: Database manager instance
        min_score: Minimum sentiment score (default 20 for bullish)
        max_score: Maximum sentiment score (default -20 for bearish)
    
    Returns:
        List of dictionaries with symbol, sentiment score, and details
    """
    if not db_manager or not db_manager.pool:
        return []
    
    try:
        # Simply get pre-calculated sentiment scores from database
        # This uses the same data that Option Chain Analysis uses
        sentiment_results = db_manager.get_extreme_sentiment_symbols(min_score, max_score)
        
        # Filter to only current (earliest) expiry for each symbol
        # This matches what Option Chain Analysis shows
        if sentiment_results:
            # Get current expiry for each symbol
            symbols_data = db_manager.get_all_symbols_with_latest_data()
            if symbols_data:
                current_expiry_map = {s['symbol']: s['expiry_date'] for s in symbols_data}
                
                # Filter to only include sentiment for current expiry
                filtered_results = []
                for result in sentiment_results:
                    symbol = result['symbol']
                    if symbol in current_expiry_map:
                        if result['expiry_date'] == current_expiry_map[symbol]:
                            filtered_results.append(result)
                
                sentiment_results = filtered_results
        
        # If no sentiment scores found, show message
        if not sentiment_results:
            st.info("ℹ️ No sentiment scores found for current expiry.")
            st.info("💡 Background service calculates sentiment automatically. Please wait for data collection.")
            return []
        
        return sentiment_results
        
    except Exception as e:
        st.error(f"Error getting sentiment data: {str(e)}")
        return []


def calculate_sentiment_with_itm_filter(db_manager: TimescaleDBManager, symbol: str, expiry_date: str, itm_count: int) -> Optional[Dict]:
    """
    Calculate sentiment for a symbol using ITM filtering (same as Option Chain Analysis)
    
    Args:
        db_manager: Database manager
        symbol: Symbol name
        expiry_date: Expiry date
        itm_count: Number of ITM strikes to include (same as Option Chain Analysis)
    
    Returns:
        Dictionary with sentiment data or None
    """
    try:
        # Get raw option chain data from database
        # get_latest_option_chain already returns data in API format: [{strike_price, call_options, put_options}, ...]
        data = db_manager.get_latest_option_chain(symbol, expiry_date)
        if not data:
            return None
        
        # Get spot price from first strike (database already includes it)
        spot_price = 0
        if data and len(data) > 0:
            # Try to get from first strike's underlying_spot_price or use spot_price from database
            spot_price = data[0].get('underlying_spot_price', 0)
            if spot_price == 0:
                # Get from database query
                with db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT spot_price 
                            FROM option_chain_data 
                            WHERE symbol = %s AND expiry_date = %s 
                            AND spot_price > 0
                            ORDER BY timestamp DESC 
                            LIMIT 1
                        """, (symbol, expiry_date))
                        result = cur.fetchone()
                        if result and result[0] and result[0] > 0:
                            spot_price = float(result[0])
        
        if spot_price == 0:
            # Use middle strike as approximation
            strikes = [s.get('strike_price', 0) for s in data if s.get('strike_price', 0) > 0]
            if strikes:
                strikes.sort()
                spot_price = strikes[len(strikes) // 2]
        
        if spot_price == 0:
            return None
        
        # Get spot price from database
        spot_price = 0
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT spot_price 
                    FROM option_chain_data 
                    WHERE symbol = %s AND expiry_date = %s 
                    AND spot_price > 0
                    ORDER BY timestamp DESC 
                    LIMIT 1
                """, (symbol, expiry_date))
                result = cur.fetchone()
                if result and result[0] and result[0] > 0:
                    spot_price = float(result[0])
        
        if spot_price == 0:
            return None
        
        # Process option chain data
        processed_data = process_option_chain_data(data, spot_price)
        if not processed_data:
            return None
        
        # Convert to DataFrame and clean
        table = pd.DataFrame(processed_data)
        table = table.dropna(subset=['Strike'])
        table = table[table['Strike'] > 0]
        table = table.sort_values('Strike').reset_index(drop=True)
        table = table.drop_duplicates(subset=["Strike"], keep='first')
        
        if len(table) == 0:
            return None
        
        # Apply ITM filtering (same as Option Chain Analysis)
        atm_strike = table.loc[table["Strike"].sub(spot_price).abs().idxmin(), "Strike"]
        below_atm = table[table["Strike"] < atm_strike].tail(itm_count)
        above_atm = table[table["Strike"] > atm_strike].head(itm_count)
        atm_row = table[table["Strike"] == atm_strike]
        
        # Combine filtered parts
        filtered_parts = []
        if not below_atm.empty:
            filtered_parts.append(below_atm)
        if not atm_row.empty:
            filtered_parts.append(atm_row)
        if not above_atm.empty:
            filtered_parts.append(above_atm)
        
        if not filtered_parts:
            return None
        
        filtered_table = pd.concat(filtered_parts, axis=0, ignore_index=True)
        filtered_table = filtered_table.sort_values('Strike').reset_index(drop=True)
        
        # Calculate sentiment using filtered data
        bucket_summary = calculate_bucket_summaries(filtered_table, atm_strike, spot_price)
        pcr_data = calculate_comprehensive_pcr(bucket_summary)
        sentiment_analysis = calculate_comprehensive_sentiment_score(
            filtered_table, bucket_summary, pcr_data, spot_price
        )
        
        return {
            'symbol': symbol,
            'expiry_date': expiry_date,
            'sentiment_score': sentiment_analysis['final_score'],
            'sentiment': sentiment_analysis['sentiment'],
            'confidence': sentiment_analysis['confidence'],
            'spot_price': spot_price
        }
    except Exception as e:
        st.error(f"Error calculating sentiment for {symbol}: {str(e)}")
        return None


def display_sentiment_dashboard(db_manager: TimescaleDBManager):
    """Display two simple tables (bullish/bearish) with stock name and sentiment score"""
    
    st.header("📊 Sentiment Dashboard - Extreme Signals")
    
    # Settings: ITM count and thresholds
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    with col1:
        itm_count = st.radio("ITM Strikes", [1, 2, 3, 5], index=2, key="sentiment_itm_count")
    with col2:
        bullish_threshold = st.number_input("Bullish Threshold", min_value=0, max_value=100, value=20, step=5, key="bullish_thresh")
    with col3:
        bearish_threshold = st.number_input("Bearish Threshold", min_value=-100, max_value=0, value=-20, step=5, key="bearish_thresh")
    with col4:
        st.write("")  # Spacing
        if st.button("🔄 Refresh", type="primary"):
            st.rerun()
    
    # Get all symbols with data
    with st.spinner("Calculating sentiment scores with ITM filtering..."):
        symbols_data = db_manager.get_all_symbols_with_latest_data()
        
        if not symbols_data:
            st.info("ℹ️ No data available. Background service is collecting data.")
            return
        
        # Calculate sentiment for each symbol with ITM filtering
        sentiment_results = []
        for symbol_info in symbols_data:
            symbol = symbol_info['symbol']
            expiry = symbol_info['expiry_date']
            
            sentiment_data = calculate_sentiment_with_itm_filter(
                db_manager, symbol, expiry, itm_count
            )
            
            if sentiment_data:
                sentiment_results.append(sentiment_data)
        
        # Filter by thresholds
        bullish_symbols = [
            s for s in sentiment_results 
            if s['sentiment_score'] > bullish_threshold
        ]
        bearish_symbols = [
            s for s in sentiment_results 
            if s['sentiment_score'] < bearish_threshold
        ]
        
        # Sort by absolute score
        bullish_symbols.sort(key=lambda x: x['sentiment_score'], reverse=True)  # Highest first
        bearish_symbols.sort(key=lambda x: x['sentiment_score'])  # Lowest first (ascending is default)
    
    # Display two tables side by side
    if bullish_symbols or bearish_symbols:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"🟢 Strong Bullish (Score > {bullish_threshold})")
            if bullish_symbols:
                bullish_df = pd.DataFrame(bullish_symbols)
                bullish_df = bullish_df[['symbol', 'sentiment_score']]
                bullish_df.columns = ['Stock Name', 'Sentiment Score']
                bullish_df['Sentiment Score'] = bullish_df['Sentiment Score'].apply(lambda x: f"{x:.2f}")
                
                # Add view button column
                for idx, row in bullish_df.iterrows():
                    symbol = row['Stock Name']
                    col_name, col_score, col_btn = st.columns([3, 2, 2])
                    with col_name:
                        st.write(f"**{symbol}**")
                    with col_score:
                        st.write(f"**{row['Sentiment Score']}**")
                    with col_btn:
                        if st.button("View", key=f"bullish_view_{symbol}_{idx}"):
                            st.session_state.selected_symbol = symbol
                            st.session_state.switch_to_option_chain = True
                            st.rerun()
            else:
                st.info("No bullish signals found")
        
        with col2:
            st.subheader(f"🔴 Strong Bearish (Score < {bearish_threshold})")
            if bearish_symbols:
                bearish_df = pd.DataFrame(bearish_symbols)
                bearish_df = bearish_df[['symbol', 'sentiment_score']]
                bearish_df.columns = ['Stock Name', 'Sentiment Score']
                bearish_df['Sentiment Score'] = bearish_df['Sentiment Score'].apply(lambda x: f"{x:.2f}")
                
                # Add view button column
                for idx, row in bearish_df.iterrows():
                    symbol = row['Stock Name']
                    col_name, col_score, col_btn = st.columns([3, 2, 2])
                    with col_name:
                        st.write(f"**{symbol}**")
                    with col_score:
                        st.write(f"**{row['Sentiment Score']}**")
                    with col_btn:
                        if st.button("View", key=f"bearish_view_{symbol}_{idx}"):
                            st.session_state.selected_symbol = symbol
                            st.session_state.switch_to_option_chain = True
                            st.rerun()
            else:
                st.info("No bearish signals found")
    else:
        st.info("ℹ️ No symbols found with extreme sentiment scores for the selected thresholds.")

