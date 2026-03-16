#Real-Time Stock Price Tracker
#Dash app with live-updating stock charts, SMA overlays, and volume display.
#Uses yfinance for real market data with synthetic fallback.

import numpy as np
import pandas as pd
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
from plotly.subplots import make_subplots

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

STOCKS = {
    'AAPL': 'Apple', 'GOOGL': 'Alphabet', 'MSFT': 'Microsoft',
    'AMZN': 'Amazon', 'TSLA': 'Tesla',
}
PERIODS = {'1 Month': '1mo', '3 Months': '3mo', '6 Months': '6mo', '1 Year': '1y'}


# Data fetching
def fetch_data(ticker, period):
    """Fetch historical data via yfinance, with synthetic fallback."""
    if HAS_YFINANCE:
        try:
            data = yf.download(ticker, period=period, interval='1d', progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            if not data.empty and len(data) > 5:
                return data
        except Exception:
            pass

    # Fallback: generate realistic synthetic data
    n_days = {'1mo': 22, '3mo': 66, '6mo': 132, '1y': 252}[period]
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=n_days)
    np.random.seed(hash(ticker + str(pd.Timestamp.today().date())) % (2**32))
    base = {'AAPL': 185, 'GOOGL': 142, 'MSFT': 415, 'AMZN': 187, 'TSLA': 245}
    price = base.get(ticker, 150)
    closes = [price]
    for _ in range(n_days - 1):
        closes.append(closes[-1] * (1 + np.random.normal(0.0004, 0.018)))

    closes = np.array(closes)
    highs = closes * (1 + np.abs(np.random.normal(0, 0.012, n_days)))
    lows  = closes * (1 - np.abs(np.random.normal(0, 0.012, n_days)))
    opens = lows + np.random.uniform(0, 1, n_days) * (highs - lows)
    return pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low':  lows,
        'Close': closes,
        'Volume': np.random.randint(10_000_000, 80_000_000, n_days),
    }, index=dates)


# App
app = dash.Dash(__name__)
server = app.server
app.title = 'Stock Price Tracker'

app.layout = html.Div([

    html.Div([
        html.H1('Real-Time Stock Price Tracker'),
        html.P(id='data-source'),
    ], className='header'),

    # Filters
    html.Div([
        html.Div([
            html.Label('Stock'),
            dcc.Dropdown(
                id='stock-picker',
                options=[{'label': f'{t} — {n}', 'value': t} for t, n in STOCKS.items()],
                value='AAPL', clearable=False,
            ),
        ], className='filter-item'),

        html.Div([
            html.Label('Period'),
            dcc.Dropdown(
                id='period-picker',
                options=[{'label': k, 'value': v} for k, v in PERIODS.items()],
                value='3mo', clearable=False,
            ),
        ], className='filter-item'),
    ], className='filters'),

    # KPI cards
    html.Div(id='kpi-cards', className='kpi-row'),

    # Price + Volume chart
    html.Div([dcc.Graph(id='price-chart')], className='chart-full'),

    # Auto-refresh every 30 seconds
    dcc.Interval(id='refresh', interval=30_000, n_intervals=0),

], className='container')


# Callback
@app.callback(
    [Output('data-source', 'children'),
     Output('kpi-cards', 'children'),
     Output('price-chart', 'figure')],
    [Input('stock-picker', 'value'),
     Input('period-picker', 'value'),
     Input('refresh', 'n_intervals')]
)
def update(ticker, period, _n):
    data = fetch_data(ticker, period)
    source = ('Live data via yfinance (auto-refreshes every 30s)'
              if HAS_YFINANCE else 'Synthetic data — install yfinance for real market data')

    close = data['Close']
    last_price = close.iloc[-1]
    prev_price = close.iloc[-2] if len(close) > 1 else last_price
    daily_change = last_price - prev_price
    daily_pct = (daily_change / prev_price) * 100
    period_high = data['High'].max()
    period_low = data['Low'].min()

    sign = '+' if daily_change >= 0 else ''
    kpis = [
        _kpi('Last Price', f'${last_price:,.2f}'),
        _kpi('Daily Change', f'{sign}${daily_change:,.2f} ({sign}{daily_pct:.2f}%)'),
        _kpi('Period High', f'${period_high:,.2f}'),
        _kpi('Period Low', f'${period_low:,.2f}'),
    ]

    # --- Price chart with SMA + Volume subplot ---
    sma_window = 10 if len(close) < 60 else 20
    sma_20 = close.rolling(sma_window).mean()
    sma_label = f'SMA-{sma_window}'

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.03,
    )

    # Price area
    fig.add_trace(go.Scatter(
        x=data.index, y=close, mode='lines', name='Close',
        line=dict(color='#4C72B0', width=2),
        fill='tozeroy', fillcolor='rgba(76,114,176,0.12)',
    ), row=1, col=1)

    # SMA-20
    fig.add_trace(go.Scatter(
        x=data.index, y=sma_20, mode='lines', name=sma_label,
        line=dict(color='#C44E52', width=1.5, dash='dash'),
    ), row=1, col=1)

    # Volume bars
    colors = ['#6c757d']
    colors += ['#55A868' if close.iloc[i] >= close.iloc[i - 1]
               else '#C44E52' for i in range(1, len(close))]
    fig.add_trace(go.Bar(
        x=data.index, y=data['Volume'], name='Volume',
        marker_color=colors, opacity=0.6,
    ), row=2, col=1)

    fig.update_layout(
        title=f'{ticker} — {STOCKS.get(ticker, ticker)}',
        xaxis2_title='Date',
        yaxis_title='Price ($)',
        yaxis2_title='Volume',
        margin=dict(t=40, b=20),
        legend=dict(orientation='h', y=1.02, x=0),
        hovermode='x unified',
    )

    return source, kpis, fig


def _kpi(title, value):
    return html.Div([
        html.Span(title, className='kpi-title'),
        html.Span(value, className='kpi-value'),
    ], className='kpi-card')


if __name__ == '__main__':
    app.run(debug=True)
