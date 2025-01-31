import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import pytz
import time

def get_yf_data(ticker, start_date, end_date, apply_delay=False, retries=3):
    """
    Fetch data from yfinance with optional 20-minute delay
    """
    for attempt in range(retries):
        try:
            stock = yf.download(ticker,
                              start=start_date,
                              end=end_date,
                              interval='1m',
                              progress=False)

            if not stock.empty:
                if apply_delay:
                    # Apply 20-minute delay by shifting the data forward
                    current_time = datetime.now(pytz.UTC)
                    delay_mask = stock.index <= (current_time - timedelta(minutes=20))
                    stock = stock[delay_mask]
                return stock
            time.sleep(1)
        except Exception as e:
            if attempt == retries - 1:
                st.error(f"Failed to fetch data for {ticker} after {retries} attempts: {str(e)}")
            time.sleep(1)
    return None

def should_apply_delay():
    """
    Determine if we should apply delay based on current time
    Returns: bool
    """
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    now = datetime.now(tz)

    # Create time objects for comparison
    market_start = now.replace(hour=11, minute=30, second=0, microsecond=0)
    market_end = now.replace(hour=17, minute=0, second=0, microsecond=0)

    # Convert current time to comparable format
    current_time = now.replace(microsecond=0)

    # Return True only if we're between 11:30 and 17:00
    return market_start <= current_time < market_end

def get_prices_and_calculate(arg_ticker, us_ticker):
    try:
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        now = datetime.now(tz)
        start_date = now.date() - timedelta(days=1)
        end_date = now.date() + timedelta(days=1)

        # Check if we should apply delay to US data
        apply_us_delay = should_apply_delay()

        result = {
            'arg_price': None,
            'us_price_17': None,
            'us_price_18': None,
            'arg_time': None,
            'us_time': None,
            'time_17': None,
            'delayed_status': 'DELAYED' if apply_us_delay else 'REAL-TIME'
        }

        # Fetch Argentine data (always delayed by 20 minutes)
        arg_data = get_yf_data(f"{arg_ticker}.BA", start_date, end_date, apply_delay=True)
        if arg_data is not None and not arg_data.empty:
            result['arg_price'] = float(arg_data['Close'].iloc[-1])
            result['arg_time'] = arg_data.index[-1].tz_convert(tz).strftime('%H:%M:%S')

        # Fetch US data with conditional delay
        us_data = get_yf_data(us_ticker, start_date, end_date, apply_delay=apply_us_delay)
        if us_data is not None and not us_data.empty:
            result['us_price_18'] = float(us_data['Close'].iloc[-1])
            result['us_time'] = us_data.index[-1].tz_convert(tz).strftime('%H:%M:%S')

            # Find price closest to 17:00
            target_time = now.replace(hour=17, minute=0, second=0, microsecond=0)
            window_start = target_time - timedelta(minutes=10)
            window_end = target_time + timedelta(minutes=10)

            closest_time = None
            min_diff = timedelta(hours=24)

            for idx in us_data.index:
                try:
                    idx_time = idx.tz_convert(tz)
                    idx_time_today = idx_time.replace(year=target_time.year,
                                                    month=target_time.month,
                                                    day=target_time.day)

                    if window_start <= idx_time_today <= window_end:
                        time_diff = abs(idx_time_today - target_time)
                        if time_diff < min_diff:
                            min_diff = time_diff
                            closest_time = idx
                            result['us_price_17'] = float(us_data.loc[idx, 'Close'])
                            result['time_17'] = idx_time_today.strftime('%H:%M:%S')
                except Exception:
                    continue

        return result

    except Exception as e:
        st.error(f"Error en get_prices_and_calculate: {str(e)}")
        return None

def calculate_theoretical_price(arg_price, us_price_17, us_price_18, ratio):
    if us_price_17 == 0 or us_price_17 is None:
        return None
    pct_change = (us_price_18 - us_price_17) / us_price_17
    theoretical_price = arg_price * (1 + pct_change)
    return theoretical_price

def calculate_implied_exchange_rate(arg_price, us_price, ratio):
    if arg_price and us_price and ratio and us_price > 0:
        return (arg_price * ratio) / us_price
    return None

def main():
    st.title('Calculadora de Precios de Cierre del Mercado Argentino')

    pairs_df = pd.read_csv('TickersRatios.csv')
    selected_tickers = []

    if pairs_df is not None:
        input_method = st.radio(
            "Método de selección de tickers",
            ["Ingresar tickers manualmente", "Usar selector múltiple"]
        )

        if input_method == "Ingresar tickers manualmente":
            ticker_input = st.text_input(
                'Ingrese tickers separados por coma (ejemplo: GGAL,YPFD,NVDA,MSFT)',
                help='Ingrese los tickers argentinos separados por coma, sin espacios'
            )
            if ticker_input:
                input_tickers = [ticker.strip() for ticker in ticker_input.split(',')]
                selected_tickers = [ticker for ticker in input_tickers
                                  if ticker in pairs_df['ArgentineTicker'].values]
                invalid_tickers = set(input_tickers) - set(selected_tickers)
                if invalid_tickers:
                    st.warning(f"Tickers no válidos: {', '.join(invalid_tickers)}")
        else:
            selected_tickers = st.multiselect(
                'Seleccionar Tickers Argentinos',
                pairs_df['ArgentineTicker'].tolist()
            )

        if selected_tickers:
            for arg_ticker in selected_tickers:
                row = pairs_df[pairs_df['ArgentineTicker'] == arg_ticker].iloc[0]
                us_ticker = row['WallStreetTicker']
                ratio = row['Ratio']

                st.write('---')
                st.subheader(f'Información para {arg_ticker}')
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f'🇦🇷 **Ticker Argentino:** {arg_ticker}')
                with col2:
                    st.write(f'🇺🇸 **Ticker EEUU:** {us_ticker}')
                with col3:
                    st.write(f'📊 **Ratio:** {ratio}')

                with st.spinner('Obteniendo datos del mercado...'):
                    prices = get_prices_and_calculate(arg_ticker, us_ticker)

                col1, col2, col3 = st.columns(3)

                # Argentine price
                with col1:
                    if prices and prices['arg_price'] is not None:
                        st.metric(
                            f"Cierre Argentina ({prices['arg_time']}) - DELAYED",
                            f"${prices['arg_price']:.2f}"
                        )
                        arg_price = prices['arg_price']
                    else:
                        st.warning("Precio Argentina no disponible")
                        arg_price = st.number_input(
                            "Ingrese precio Argentina",
                            min_value=0.0,
                            value=0.0,
                            step=0.01,
                            key=f"arg_price_{arg_ticker}"
                        )

                # US 17:00 price
                with col2:
                    if prices and prices['us_price_17'] is not None:
                        st.metric(
                            f"Precio EEUU {prices.get('time_17', '17:00')} GMT-3",
                            f"${prices['us_price_17']:.2f}"
                        )
                        us_price_17 = prices['us_price_17']
                    else:
                        if prices and prices.get('time_17'):
                            st.warning(f"Precio más cercano encontrado: {prices['time_17']}")
                        else:
                            st.warning("Precio EEUU 17:00 no disponible")
                        us_price_17 = st.number_input(
                            "Ingrese precio EEUU 17:00",
                            min_value=0.0,
                            value=0.0,
                            step=0.01,
                            key=f"us_price_17_{arg_ticker}"
                        )

                # US current price
                with col3:
                    if prices and prices['us_price_18'] is not None:
                        st.metric(
                            f"Cierre EEUU ({prices['us_time']}) - {prices['delayed_status']}",
                            f"${prices['us_price_18']:.2f}"
                        )
                        us_price_current = prices['us_price_18']
                    else:
                        st.warning("Precio EEUU actual no disponible")
                        us_price_current = st.number_input(
                            "Ingrese precio EEUU actual",
                            min_value=0.0,
                            value=0.0,
                            step=0.01,
                            key=f"us_price_current_{arg_ticker}"
                        )

                # Calculate theoretical price
                if all(v > 0 for v in [arg_price, us_price_17, us_price_current]):
                    theoretical_price = calculate_theoretical_price(
                        arg_price,
                        us_price_17,
                        us_price_current,
                        ratio
                    )

                    if theoretical_price:
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric(
                                "Precio Teórico",
                                f"${theoretical_price:.2f}"
                            )
                        with col2:
                            diff = theoretical_price - arg_price
                            pct_change = ((theoretical_price / arg_price) - 1) * 100
                            st.metric(
                                "Diferencia",
                                f"${diff:.2f}",
                                f"{pct_change:+.2f}%"
                            )

                    # Add implied exchange rate calculations
                    st.write("---")
                    st.write("**Tipo de Cambio Implícito:**")
                    col1, col2 = st.columns(2)

                    implied_rate_17 = calculate_implied_exchange_rate(arg_price, us_price_17, ratio)
                    implied_rate_current = calculate_implied_exchange_rate(arg_price, us_price_current, ratio)

                    with col1:
                        if implied_rate_17:
                            st.metric(
                                f"TC Implícito 17:00",
                                f"${implied_rate_17:.2f}"
                            )

                    with col2:
                        if implied_rate_current:
                            st.metric(
                                f"TC Implícito {prices['us_time'] if prices and prices.get('us_time') else 'Actual'}",
                                f"${implied_rate_current:.2f}"
                            )

        with st.expander('Mostrar Información de Depuración'):
            st.write('Información de Depuración:')
            st.write(f'Hora actual (Argentina): {datetime.now(pytz.timezone("America/Argentina/Buenos_Aires"))}')
            if 'prices' in locals():
                st.write('Datos de precios:', {
                    'Precio Argentina': prices.get('arg_price'),
                    'Precio EEUU 17:00': prices.get('us_price_17'),
                    'Precio EEUU actual': prices.get('us_price_18'),
                    'Hora Argentina': prices.get('arg_time'),
                    'Hora EEUU': prices.get('us_time'),
                    'Hora precio 17:00': prices.get('time_17'),
                    'Estado delay US': prices.get('delayed_status')
                })

        if st.button('🔄 Actualizar Precios'):
            st.rerun()

if __name__ == '__main__':
    main()
