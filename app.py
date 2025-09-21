from flask import Flask, render_template_string, request, jsonify
import requests, time

app = Flask(__name__)

# In-memory stores
signal_capture = {}   # { 'BTCINR': [ { 'buy_price': float, 'timestamp': int } ] }
realized_profits = [] # [ { 'market': str, 'buy_price': float, 'sell_price': float, 'pl_value': float, 'pl_percent': float } ]

def fetch_tickers():
    url = "https://api.coindcx.com/exchange/ticker"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print("Error fetching tickers:", e)
    return []

@app.route('/')
def index():
    tickers = fetch_tickers()
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CoinDCX Monitor + Signal Capture</title>
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <link href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" rel="stylesheet" />
        <script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {
                font-family: Arial, sans-serif;
                padding: 20px;
                margin: 0;
                background-color: #f9f9f9;
            }

            .ticker-block {
                border: 1px solid #ddd;
                padding: 15px;
                margin: 10px 0;
                border-radius: 8px;
                background: #fff;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                flex: 1 1 100%;
            }

            table {
                border-collapse: collapse;
                margin-top: 10px;
                width: 100%;
            }

            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
                word-break: break-word;
            }

            th {
                background: #f4f4f4;
            }

            button {
                padding: 10px 14px;
                margin: 5px 0;
                font-size: 16px;
                cursor: pointer;
            }

            select, label {
                margin: 5px;
                font-size: 16px;
            }

            #tickersContainer {
                display: flex;
                flex-wrap: wrap;
                gap: 20px;
            }

            @media (min-width: 600px) {
                .ticker-block {
                    flex: 1 1 calc(50% - 20px);
                }
            }

            @media (min-width: 900px) {
                .ticker-block {
                    flex: 1 1 calc(33.33% - 20px);
                }
            }

            canvas {
                max-width: 100% !important;
                height: auto !important;
            }

            .select2-container {
                min-width: 250px;
            }

            h2, h3 {
                margin-top: 0;
            }
        </style>
        <script>
            let charts = {};
            let refreshInterval = 5000;
            let intervalId;

            function initChart(canvasId){
                const ctx = document.getElementById(canvasId).getContext('2d');
                return new Chart(ctx, {
                    type: 'line',
                    data: { labels: [], datasets:[{ label:'Last Price', data:[], borderColor:'blue', fill:false, tension:0.3 }] },
                    options: { responsive:true, scales:{ x:{ display:true }, y:{ display:true } } }
                });
            }

            function updateChart(chart, time, price){
                if(chart.data.labels.length > 20){ chart.data.labels.shift(); chart.data.datasets[0].data.shift(); }
                chart.data.labels.push(time); chart.data.datasets[0].data.push(price); chart.update();
            }

            function fetchDataForTicker(ticker){
                fetch(`/ticker_data?ticker=${ticker}`)
                .then(resp=>resp.json())
                .then(data=>{
                    if(!data.error){
                        let price=parseFloat(data.last_price).toFixed(2);
                        let time=new Date(data.timestamp).toLocaleTimeString();
                        document.getElementById(`table-${ticker}`).innerHTML=`
                            <tr><th>Market</th><td>${data.market}</td></tr>
                            <tr><th>Last Price</th><td>₹${price}</td></tr>
                            <tr><th>High</th><td>₹${parseFloat(data.high).toFixed(2)}</td></tr>
                            <tr><th>Low</th><td>₹${parseFloat(data.low).toFixed(2)}</td></tr>
                        `;
                        updateChart(charts[ticker], time, parseFloat(price));
                    }
                });
            }

            function fetchData(){
                let selected=$('#tickerSelect').val();
                if(!selected) return;
                selected.forEach(t=>fetchDataForTicker(t));
                updateSignalTable();
            }

            function setRefreshInterval(){
                let val=parseInt($('#refreshSelect').val())*1000;
                refreshInterval=val;
                if(intervalId) clearInterval(intervalId);
                intervalId=setInterval(fetchData, refreshInterval);
            }

            function renderSelectedTickers(){
                let container=document.getElementById("tickersContainer");
                container.innerHTML="";
                let selected=$('#tickerSelect').val();
                if(!selected) return;
                selected.forEach(ticker=>{
                    container.innerHTML+=`
                        <div class="ticker-block">
                            <h3>${ticker}</h3>
                            <button onclick="buyTicker('${ticker}')">Buy</button>
                            <table id="table-${ticker}"><tr><td colspan="2">Loading...</td></tr></table>
                            <canvas id="chart-${ticker}" height="100"></canvas>
                        </div>
                    `;
                    charts[ticker]=initChart(`chart-${ticker}`);
                });
                fetchData();
                setRefreshInterval();
            }

            function buyTicker(ticker){
                fetch(`/buy?ticker=${ticker}`)
                .then(resp=>resp.json())
                .then(data=>{
                    alert(`Bought ${ticker} at ₹${data.buy_price}`);
                });
            }

            function sellTicker(ticker,index){
                fetch(`/sell?ticker=${ticker}&index=${index}`)
                .then(resp=>resp.json())
                .then(data=>{
                    if(!data.error){
                        alert(`Sold ${ticker} at ₹${data.sell_price} (P/L: ₹${data.profit.toFixed(2)})`);
                        updateSignalTable();
                    } else {
                        alert(data.error);
                    }
                });
            }

            function updateSignalTable(){
                fetch('/signals')
                .then(resp=>resp.json())
                .then(data=>{
                    let html=`<tr><th>Market</th><th>Buy Price</th><th>Current Price</th><th>P/L ₹</th><th>P/L %</th><th>Action</th></tr>`;
                    data.forEach((sig,idx)=>{
                        html+=`<tr>
                            <td>${sig.market}</td>
                            <td>₹${sig.buy_price.toFixed(2)}</td>
                            <td>₹${sig.current_price.toFixed(2)}</td>
                            <td>₹${sig.pl_value.toFixed(2)}</td>
                            <td>${sig.pl_percent.toFixed(2)}%</td>
                            <td><button onclick="sellTicker('${sig.market}',${sig.index})">Sell</button></td>
                        </tr>`;
                    });
                    document.getElementById("signalTable").innerHTML=html;
                });
            }

            $(document).ready(function(){
                $('#tickerSelect').select2();
            });
        </script>
    </head>
    <body>
        <h2>Sajid Shaikh Testing Terminal</h2>
        <p>Call: 9834370368</p>

        <div>
            <label>Select Markets:</label>
            <select id="tickerSelect" multiple onchange="renderSelectedTickers()">
                {% for t in tickers %}
                    <option value="{{ t['market'] }}">{{ t['market'] }}</option>
                {% endfor %}
            </select>

            <label>Refresh Interval:</label>
            <select id="refreshSelect" onchange="setRefreshInterval()">
                <option value="2">2s</option>
                <option value="5" selected>5s</option>
                <option value="10">10s</option>
                <option value="30">30s</option>
            </select>
        </div>

        <h3>Active Trades</h3>
        <table id="signalTable">
            <tr><td colspan="6">No active signals</td></tr>
        </table>

        <div id="tickersContainer"></div>
    </body>
    </html>
    """
    return render_template_string(html, tickers=tickers)

@app.route('/buy')
def buy():
    ticker = request.args.get("ticker")
    tickers = fetch_tickers()
    for t in tickers:
        if t['market'] == ticker:
            buy_entry = {'buy_price': float(t['last_price']), 'timestamp': int(time.time())}
            signal_capture.setdefault(ticker, []).append(buy_entry)
            return jsonify({'market': ticker, 'buy_price': buy_entry['buy_price']})
    return jsonify({'error':'Ticker not found'}),404

@app.route('/sell')
def sell():
    ticker = request.args.get("ticker")
    index = request.args.get("index", type=int, default=None)
    tickers = fetch_tickers()

    if ticker in signal_capture and signal_capture[ticker]:
        if index is not None and 0 <= index < len(signal_capture[ticker]):
            for t in tickers:
                if t['market'] == ticker:
                    sell_price = float(t['last_price'])
                    buy_entry = signal_capture[ticker].pop(index)
                    pl_value = sell_price - buy_entry['buy_price']
                    pl_percent = (pl_value / buy_entry['buy_price'])*100
                    realized_profits.append({
                        'market': ticker,
                        'buy_price': buy_entry['buy_price'],
                        'sell_price': sell_price,
                        'pl_value': pl_value,
                        'pl_percent': pl_percent
                    })
                    if not signal_capture[ticker]:
                        del signal_capture[ticker]
                    return jsonify({'market': ticker, 'sell_price': sell_price, 'profit': pl_value})
        return jsonify({'error':'Invalid index'}),400
    return jsonify({'error':'Ticker not in signal list'}),404

@app.route('/signals')
def signals():
    tickers = fetch_tickers()
    results = []
    for market, buys in signal_capture.items():
        current_price = next((float(t['last_price']) for t in tickers if t['market']==market), 0)
        for idx, buy in enumerate(buys):
            buy_price = buy['buy_price']
            pl_value = current_price - buy_price
            pl_percent = (pl_value / buy_price * 100) if buy_price else 0
            results.append({
                'market': market,
                'buy_price': buy_price,
                'current_price': current_price,
                'pl_value': pl_value,
                'pl_percent': pl_percent,
                'index': idx
            })
    return jsonify(results)

@app.route('/profits')
def profits():
    return jsonify(realized_profits)

@app.route('/ticker_data')
def ticker_data():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error":"Ticker is required"}),400
    tickers = fetch_tickers()
    for t in tickers:
        if t['market']==ticker:
            return jsonify(t)
    return jsonify({"error":f"No data found for {ticker}"}),404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
