import { AIEngine } from './ai-engine.js';
import { ChartManager } from './chart-manager.js';
import { PortfolioManager } from './portfolio.js';

function formatPrice(price) {
  if (price === undefined || price === null || isNaN(price)) return '---';
  const val = Number(price);
  if (val >= 1000) {
    return '$' + val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } else if (val >= 1) {
    return '$' + val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  } else {
    return '$' + val.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 });
  }
}

class AppController {
  constructor() {
    this.aiEngine = new AIEngine();
    this.chartManager = new ChartManager('cryptoChart');
    this.portfolio = new PortfolioManager();

    this.symbols = [
      'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ZECUSDT', 'XLMUSDT', 
      'TAOUSDT', 'POLUSDT', 'ONDOUSDT', 'GRAMUSDT', 'LINKUSDT', 
      'APTUSDT', 'LTCUSDT', 'THETAUSDT', 'AVAXUSDT', 'BCHUSDT', 
      'SUIUSDT', 'RUNEUSDT', 'RENDERUSDT', 'OPUSDT', 'INJUSDT', 
      'HBARUSDT', 'DOGEUSDT', 'ARBUSDT', 'ADAUSDT', 'XRPUSDT', 
      'NEARUSDT', 'ATOMUSDT', 'AAVEUSDT', 'DOTUSDT', 'ETCUSDT', 
      'FILUSDT', 'UNIUSDT', 'SANDUSDT'
    ];
    this.activeSymbol = 'BTCUSDT';
    this.activeTimeframe = '15m';
    this.activeStrategyMode = 'daytrade';
    
    this.tickerData = {};
    this.priceHistories = {};
    this.currentSignal = null;
    this.predictionCurve = [];

    this.init();
  }

  async init() {
    this.bindEvents();
    
    // Initial fetch for tickers and ACTIVE symbol FIRST for immediate UI rendering!
    await this.fetchAllMarketTickers();
    await this.fetchSymbolKlines(this.activeSymbol, this.activeTimeframe);

    this.renderTickerBar();
    this.runAIAnalysis();
    this.updatePortfolioUI();
    await this.fetchBackendState();

    // Asynchronously fetch remaining symbols in background
    this.symbols.filter(s => s !== this.activeSymbol).forEach(sym => {
      this.fetchSymbolKlines(sym, this.activeTimeframe);
    });

    // Real Live Polling from Binance API (Every 3.5 seconds)
    setInterval(() => this.realtimePoll(), 3500);

    // Auto-Pilot Check Loop (Every 15 seconds)
    setInterval(() => this.autoPilotCheck(), 15000);
  }

  /**
   * Fetch 24h Real-time Tickers from Binance (Data Vision Mirror)
   */
  async fetchAllMarketTickers() {
    try {
      const res = await fetch('https://data-api.binance.vision/api/v3/ticker/24hr');
      if (res.ok) {
        const data = await res.json();
        data.forEach(item => {
          if (this.symbols.includes(item.symbol)) {
            const price = parseFloat(item.lastPrice);
            this.tickerData[item.symbol] = {
              symbol: item.symbol,
              price: price,
              change24h: parseFloat(item.priceChangePercent).toFixed(2)
            };
          }
        });
      }
    } catch (err) {
      console.warn("Binance 24hr Ticker fetch mirror fallback:", err);
      for (const sym of this.symbols) {
        await this.fetchSingleTicker(sym);
      }
    }
  }

  async fetchSingleTicker(sym) {
    try {
      const res = await fetch(`https://data-api.binance.vision/api/v3/ticker/24hr?symbol=${sym}`);
      if (res.ok) {
        const item = await res.json();
        this.tickerData[sym] = {
          symbol: sym,
          price: parseFloat(item.lastPrice),
          change24h: parseFloat(item.priceChangePercent).toFixed(2)
        };
      }
    } catch (e) {
      console.error(`Failed to fetch ticker for ${sym}`, e);
    }
  }

  /**
   * Fetch Real Historical Candlestick (Klines) with Multi-Source Fallbacks
   */
  async fetchSymbolKlines(symbol, interval = '15m') {
    let success = false;
    const fetchUrls = [
      `https://data-api.binance.vision/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=100`,
      `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=100`,
      `/api/klines?symbol=${symbol}&interval=${interval}&limit=100`
    ];

    for (const url of fetchUrls) {
      try {
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            const prices = data.map(candle => parseFloat(candle[4]));
            this.priceHistories[symbol] = prices;

            if (!this.tickerData[symbol]) {
              this.tickerData[symbol] = { symbol, price: prices[prices.length - 1], change24h: '0.50' };
            } else {
              this.tickerData[symbol].price = prices[prices.length - 1];
            }
            success = true;
            break;
          }
        }
      } catch (err) {
        // try next fallback
      }
    }

    if (!success && !this.priceHistories[symbol]) {
      // Fallback synthetic price series so UI never stays at $0.00
      const basePrices = { BTCUSDT: 64500, ETHUSDT: 1860, SOLUSDT: 74, AVAXUSDT: 22, BNBUSDT: 560, NEARUSDT: 4.5, LINKUSDT: 8.2, XRPUSDT: 0.55, DOGEUSDT: 0.12, SUIUSDT: 1.8 };
      const base = basePrices[symbol] || 100;
      const synth = [];
      let cur = base;
      for (let i = 0; i < 40; i++) {
        cur *= (1 + (Math.random() - 0.49) * 0.005);
        synth.push(parseFloat(cur.toFixed(4)));
      }
      this.priceHistories[symbol] = synth;
      if (!this.tickerData[symbol]) {
        this.tickerData[symbol] = { symbol, price: synth[synth.length - 1], change24h: '0.00' };
      }
    }
  }

  async realtimePoll() {
    // 1. Refresh Tickers
    await this.fetchAllMarketTickers();
    this.renderTickerBar();

    // 2. Fetch Latest Klines for active symbol
    await this.fetchSymbolKlines(this.activeSymbol, this.activeTimeframe);

    const activePrices = this.priceHistories[this.activeSymbol];
    if (activePrices && activePrices.length > 0) {
      const indicators = this.aiEngine.calculateIndicators(activePrices);
      this.chartManager.renderChart(activePrices, indicators, this.predictionCurve);
    }

    // 3. Update Portfolio Mark Prices with real market prices
    const currentPricesMap = {};
    this.symbols.forEach(s => {
      currentPricesMap[s] = this.tickerData[s] ? this.tickerData[s].price : 0;
    });
    this.portfolio.updateMarkPrices(currentPricesMap);
    this.updatePortfolioUI();
    await this.fetchBackendState();
  }

  bindEvents() {
    // Timeframe selector
    document.querySelectorAll('.tf-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.activeTimeframe = e.target.dataset.tf;
        
        await this.fetchSymbolKlines(this.activeSymbol, this.activeTimeframe);
        this.runAIAnalysis();
      });
    });

    // Target Profit Strategy selector
    document.querySelectorAll('.strategy-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.strategy-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        this.activeStrategyMode = e.target.dataset.strategy;
        this.runAIAnalysis();
      });
    });

    // Run Analysis Button
    const btnRun = document.getElementById('btnRunAnalysis');
    if (btnRun) {
      btnRun.addEventListener('click', () => this.runAIAnalysis());
    }

    // Execute Trade Button
    const btnTrade = document.getElementById('btnExecuteTrade');
    if (btnTrade) {
      btnTrade.addEventListener('click', async () => {
        if (this.currentSignal) {
          try {
            const res = await fetch('/api/open-trade', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ signal: this.currentSignal, amount: 1000 })
            });
            if (res.ok) {
              const result = await res.json();
              if (result.success) {
                this.updatePortfolioUI();
                this.logTerminalMessage(`[MANUEL İŞLEM AÇILDI] ${result.position.symbol} için ${result.position.side} pozisyonu $${result.position.entryPrice} fiyatından açıldı ve Telegram bildirimi gönderildi!`);
                return;
              }
            }
          } catch (e) {
            console.log("Local execution fallback:", e);
          }

          const pos = this.portfolio.openPositionFromSignal(this.currentSignal);
          if (pos) {
            this.updatePortfolioUI();
            this.logTerminalMessage(`[MANUEL İŞLEM AÇILDI] ${pos.symbol} için ${pos.side} pozisyonu $${pos.entryPrice} fiyatından açıldı!`);
          }
        }
      });
    }

    // Auto pilot toggle
    const autoCheck = document.getElementById('autoPilotCheck');
    if (autoCheck) {
      autoCheck.addEventListener('change', (e) => {
        this.portfolio.autoPilotEnabled = e.target.checked;
        if (e.target.checked) {
          this.logTerminalMessage('[OTOMATİK PİLOT] Gerçek Zamanlı Akıllı Alım-Satım Modu Etkinleşti.');
        } else {
          this.logTerminalMessage('[OTOMATİK PİLOT] Otomatik Mod Devre Dışı Bırakıldı.');
        }
      });
    }

    // Telegram Modal Listeners
    const openTgBtn = document.getElementById('openTelegramModal');
    const closeTgBtn = document.getElementById('closeTelegramModal');
    const tgModal = document.getElementById('telegramModal');
    const saveTgBtn = document.getElementById('saveTelegramSettings');

    if (openTgBtn && tgModal) {
      openTgBtn.addEventListener('click', () => tgModal.classList.add('active'));
    }
    if (closeTgBtn && tgModal) {
      closeTgBtn.addEventListener('click', () => tgModal.classList.remove('active'));
    }
    if (saveTgBtn) {
      saveTgBtn.addEventListener('click', async () => {
        const token = document.getElementById('tgBotToken').value.trim();
        const chatId = document.getElementById('tgChatId').value.trim();
        const enabled = document.getElementById('tgEnabledCheck').checked;

        if (enabled && (!token || !chatId)) {
          alert('Lütfen hem Bot Token hem de Chat ID alanlarını doldurunuz.');
          return;
        }

        try {
          const res = await fetch('/api/save-telegram', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bot_token: token, chat_id: chatId, enabled: enabled })
          });
          const data = await res.json();
          if (data.success) {
            alert('✅ Telegram Test Mesajı Başarıyla Gönderildi!');
            if (tgModal) tgModal.classList.remove('active');
          } else {
            alert('⚠️ Telegram Mesaj Hatası:\n' + (data.message || 'Bilinmeyen hata') + '\n\n💡 İPUCU: Telegram botunuza ilk kez mesaj göndermeden önce Telegram uygulamanızdan botu açıp "Start" (Başlat) butonuna basmanız gerekmektedir.');
          }
        } catch (e) {
          alert('Sunucu bağlantı hatası.');
        }
      });
    }

    // Grid Strategy Button listener
    const btnCreateGrid = document.getElementById('btnCreateGrid');
    if (btnCreateGrid) {
      btnCreateGrid.addEventListener('click', async () => {
        const cleanSym = this.activeSymbol.replace('USDT', '/USDT');
        const prices = this.priceHistories[this.activeSymbol];
        const curPrice = (prices && prices.length > 0) ? prices[prices.length - 1] : 60000;
        
        try {
          const res = await fetch('/api/grid/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              symbol: cleanSym,
              price: curPrice,
              support: curPrice * 0.96,
              resistance: curPrice * 1.04
            })
          });
          const result = await res.json();
          if (result.success) {
            this.logTerminalMessage(`[AI GRID STRATEJİSİ BAŞLATILDI] ${cleanSym} için Spot/Futures Grid stratejisi etkinleşti.`);
            this.fetchBackendState();
          } else {
            alert(result.message || 'Grid oluşturulamadı.');
          }
        } catch (e) {
          alert('Sunucuya bağlanılamadı.');
        }
      });
    }
  }

  async fetchBackendState() {
    try {
      const res = await fetch('/api/state');
      if (res.ok) {
        const data = await res.json();
        if (data.grid_bots) {
          this.renderGridTable(data.grid_bots);
        }
        if (data.balance) {
          this.portfolio.balance = data.balance;
        }
      }
    } catch (e) {}
  }

  renderGridTable(gridBots) {
    const gridTbody = document.getElementById('gridTbody');
    const gridCountElem = document.getElementById('gridCount');
    if (gridCountElem) gridCountElem.textContent = gridBots ? gridBots.length : 0;
    if (!gridTbody) return;

    if (!gridBots || gridBots.length === 0) {
      gridTbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; color: var(--text-dim); padding: 12px;">
            Aktif AI Grid stratejisi bulunmuyor.
          </td>
        </tr>
      `;
      return;
    }

    gridTbody.innerHTML = '';
    gridBots.forEach(g => {
      const isWin = g.realizedPnl >= 0;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${g.symbol}</strong></td>
        <td>${formatPrice(g.lowerBound)} - ${formatPrice(g.upperBound)}</td>
        <td>${g.completedStepsCount || 0} / ${g.gridCount || 6}</td>
        <td>$${(g.allocatedAmount || 350).toFixed(2)}</td>
        <td style="color: ${isWin ? 'var(--color-bullish)' : 'var(--color-bearish)'}; font-weight: 700;">
          ${isWin ? '+' : ''}$${(g.realizedPnl || 0).toFixed(2)}
        </td>
        <td><button class="btn-close-pos btn-stop-grid" data-id="${g.id}" style="background: rgba(255,23,68,0.2); border-color: rgba(255,23,68,0.5); color: #ff1744;">Durdur</button></td>
      `;
      gridTbody.appendChild(tr);
    });

    gridTbody.querySelectorAll('.btn-stop-grid').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const id = e.target.dataset.id;
        try {
          const res = await fetch('/api/grid/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
          });
          const result = await res.json();
          if (result.success) {
            this.logTerminalMessage(`[AI GRID DURDURULDU] Grid stratejisi kapatıldı.`);
            this.fetchBackendState();
            this.updatePortfolioUI();
          }
        } catch (e) {}
      });
    });
  }

  renderTickerBar() {
    const bar = document.getElementById('tickerBar');
    if (!bar) return;

    bar.innerHTML = '';
    this.symbols.forEach(sym => {
      const data = this.tickerData[sym] || { price: 0, change24h: '0.00' };
      const isUp = parseFloat(data.change24h) >= 0;
      const cleanName = sym.replace('USDT', '/USDT');

      const div = document.createElement('div');
      div.className = `ticker-item ${sym === this.activeSymbol ? 'active' : ''}`;
      div.innerHTML = `
        <span class="ticker-symbol">${cleanName}</span>
        <span class="ticker-price">${formatPrice(data.price)}</span>
        <span class="ticker-change ${isUp ? 'up' : 'down'}">${isUp ? '+' : ''}${data.change24h}%</span>
      `;
      div.addEventListener('click', async () => {
        this.activeSymbol = sym;
        document.getElementById('activePairTitle').textContent = `${cleanName} - Canlı Binance Grafiği & YZ Tahmin Eğrisi`;
        await this.fetchSymbolKlines(this.activeSymbol, this.activeTimeframe);
        this.runAIAnalysis();
      });
      bar.appendChild(div);
    });
  }

  runAIAnalysis() {
    const prices = this.priceHistories[this.activeSymbol];
    if (!prices || prices.length < 14) return;

    const indicators = this.aiEngine.calculateIndicators(prices);
    if (!indicators) return;

    const cleanSymbol = this.activeSymbol.replace('USDT', '/USDT');
    const whaleIntel = this.aiEngine.getWhaleIntelligence(cleanSymbol, indicators.currentPrice);
    const newsIntel = this.aiEngine.getNewsSentiment(cleanSymbol);

    // Generate Reasoning Steps based on Whale & News Intelligence
    const steps = this.aiEngine.generateReasoningSteps(cleanSymbol, indicators, whaleIntel, newsIntel);

    // Render Terminal Reasoning Steps
    const stepsContainer = document.getElementById('terminalSteps');
    if (stepsContainer) {
      stepsContainer.innerHTML = '';
      steps.forEach((st, idx) => {
        setTimeout(() => {
          const div = document.createElement('div');
          div.className = 'reasoning-step';
          div.innerHTML = `
            <span class="step-tag">[ADIM ${st.step}]</span>
            <span class="step-title">${st.title}:</span>
            <span class="step-desc">${st.description}</span>
          `;
          stepsContainer.appendChild(div);
          stepsContainer.parentElement.scrollTop = stepsContainer.parentElement.scrollHeight;
        }, idx * 160);
      });
    }

    const timeElem = document.getElementById('terminalTime');
    if (timeElem) timeElem.textContent = new Date().toLocaleTimeString('tr-TR');

    // Generate Trade Signal with selected Strategy Mode
    this.currentSignal = this.aiEngine.generateSignal(cleanSymbol, indicators, whaleIntel, newsIntel, this.activeStrategyMode);
    this.updateSignalCardUI(this.currentSignal);

    // Generate Prediction Curve & Update Chart
    this.predictionCurve = this.aiEngine.generatePredictionCurve(prices, this.currentSignal);
    this.chartManager.renderChart(prices, indicators, this.predictionCurve);
  }

  updateSignalCardUI(signal) {
    const badge = document.getElementById('signalTypeBadge');
    if (badge) {
      badge.textContent = signal.type;
      badge.className = `signal-type-tag ${signal.side === 'BUY' ? 'bullish' : (signal.side === 'SELL' ? 'bearish' : 'neutral')}`;
    }

    document.getElementById('signalConfidence').textContent = `%${signal.confidence}`;
    document.getElementById('signalLeverage').textContent = signal.leverage;
    document.getElementById('signalRR').textContent = signal.rrRatio;

    if (document.getElementById('signalSupport')) {
      document.getElementById('signalSupport').textContent = formatPrice(signal.supportLevel);
    }
    if (document.getElementById('signalResistance')) {
      document.getElementById('signalResistance').textContent = formatPrice(signal.resistanceLevel);
    }
    if (document.getElementById('signalPattern')) {
      document.getElementById('signalPattern').textContent = `${signal.patternName || 'Kanal İçi Hareket'} — %${signal.historicalScore || 85} Benzerlik`;
    }

    document.getElementById('signalEntry').textContent = formatPrice(signal.entryPrice);
    document.getElementById('signalTP1').textContent = formatPrice(signal.tp1);
    document.getElementById('signalTP2').textContent = formatPrice(signal.tp2);
    document.getElementById('signalTP3').textContent = formatPrice(signal.tp3);
    document.getElementById('signalSL').textContent = formatPrice(signal.sl);

    if (document.getElementById('signalTP1Pct')) document.getElementById('signalTP1Pct').textContent = signal.tp1Pct || '+3.5%';
    if (document.getElementById('signalTP2Pct')) document.getElementById('signalTP2Pct').textContent = signal.tp2Pct || '+7.0%';
    if (document.getElementById('signalTP3Pct')) document.getElementById('signalTP3Pct').textContent = signal.tp3Pct || '+12.0%';
    if (document.getElementById('signalSLPct')) document.getElementById('signalSLPct').textContent = signal.slPct || '-2.0%';

    document.getElementById('signalTime').textContent = signal.timestamp;
  }

  updatePortfolioUI() {
    document.getElementById('portBalance').textContent = `$${this.portfolio.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    document.getElementById('portEquity').textContent = `$${this.portfolio.getTotalEquity().toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    document.getElementById('winRateVal').textContent = `Kazanma Oranı: %${this.portfolio.getWinRate()}`;
    document.getElementById('posCount').textContent = this.portfolio.positions.length;

    const tbody = document.getElementById('positionsTbody');
    if (!tbody) return;

    if (this.portfolio.positions.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; color: var(--text-dim); padding: 16px;">
            Henüz açık pozisyon bulunmuyor.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = '';
    this.portfolio.positions.forEach((pos, idx) => {
      const isWin = pos.pnl >= 0;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${pos.symbol}</strong></td>
        <td><span class="${pos.side === 'LONG' ? 'badge-long' : 'badge-short'}">${pos.side}</span></td>
        <td>${formatPrice(pos.entryPrice)}</td>
        <td style="color: var(--color-accent-cyan); font-weight:600;">${formatPrice(pos.markPrice)}</td>
        <td style="color: ${isWin ? 'var(--color-bullish)' : 'var(--color-bearish)'}; font-weight: 700;">
          ${isWin ? '+' : ''}$${pos.pnl.toFixed(2)} (${isWin ? '+' : ''}${pos.pnlPercent.toFixed(2)}%)
        </td>
        <td><button class="btn-close-pos" data-idx="${idx}">Kapat</button></td>
      `;
      tbody.appendChild(tr);
    });

    tbody.querySelectorAll('.btn-close-pos').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const idx = parseInt(e.target.dataset.idx);
        this.portfolio.closePosition(idx);
        this.updatePortfolioUI();
      });
    });
  }

  autoPilotCheck() {
    if (!this.portfolio.autoPilotEnabled) return;

    if (this.currentSignal && this.currentSignal.confidence >= 86 && this.currentSignal.side !== 'HOLD') {
      const alreadyOpen = this.portfolio.positions.some(p => p.symbol === this.currentSignal.symbol);
      if (!alreadyOpen) {
        const pos = this.portfolio.openPositionFromSignal(this.currentSignal, 1000);
        if (pos) {
          this.updatePortfolioUI();
          this.logTerminalMessage(`[OTOMATİK PİLOT SİNYALİ TETİKLENDİ] %${this.currentSignal.confidence} güven oranıyla ${pos.symbol} ${pos.side} pozisyonu $${pos.entryPrice.toLocaleString()} fiyatından açıldı!`);
        }
      }
    }
  }

  logTerminalMessage(msg) {
    const stepsContainer = document.getElementById('terminalSteps');
    if (!stepsContainer) return;
    const div = document.createElement('div');
    div.className = 'reasoning-step';
    div.style.color = 'var(--color-accent-cyan)';
    div.style.fontWeight = 'bold';
    div.innerHTML = `<span class="step-tag">[SİSTEM]</span> ${msg}`;
    stepsContainer.appendChild(div);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.app = new AppController();
});
