/**
 * Sanal Portföy ve İşlem Takip Motoru (Paper Trading Manager)
 */

export class PortfolioManager {
  constructor() {
    this.balance = 10000.00; // Starting virtual balance USDT
    this.positions = [];
    this.history = [];
    this.autoPilotEnabled = false;
    this.loadFromStorage();
  }

  loadFromStorage() {
    try {
      const savedBalance = localStorage.getItem('ai_crypto_balance');
      const savedPos = localStorage.getItem('ai_crypto_positions');
      const savedHist = localStorage.getItem('ai_crypto_history');

      if (savedBalance) this.balance = parseFloat(savedBalance);
      if (savedPos) this.positions = JSON.parse(savedPos);
      if (savedHist) this.history = JSON.parse(savedHist);
    } catch (e) {
      console.warn("Storage reset to default:", e);
    }
  }

  saveToStorage() {
    try {
      localStorage.setItem('ai_crypto_balance', this.balance.toFixed(2));
      localStorage.setItem('ai_crypto_positions', JSON.stringify(this.positions));
      localStorage.setItem('ai_crypto_history', JSON.stringify(this.history));
    } catch (e) {
      console.error("Failed to save portfolio state:", e);
    }
  }

  getPositionForSymbol(symbol) {
    if (!symbol) return null;
    const clean = symbol.replace('/', '').toUpperCase();
    return this.positions.find(p => p.symbol.replace('/', '').toUpperCase() === clean) || null;
  }

  hasPositionForSymbol(symbol) {
    return !!this.getPositionForSymbol(symbol);
  }

  /**
   * Sinyalden Yeni Pozisyon Aç
   */
  openPositionFromSignal(signal, allocationAmount = 1000) {
    if (this.balance < allocationAmount) {
      alert("Yetersiz Sanal Bakiye!");
      return null;
    }

    const side = signal.side === "BUY" ? "LONG" : "SHORT";
    const entryPrice = signal.entryPrice;
    const size = parseFloat((allocationAmount / entryPrice).toFixed(4));

    // 🛡️ Mevcut Pozisyon Kontrolü
    const existing = this.getPositionForSymbol(signal.symbol);
    if (existing) {
      if (existing.side === side) {
        alert(`${signal.symbol} için zaten açık bir ${side} pozisyonunuz var!`);
        return null;
      } else {
        // Ters yönde pozisyon var: Eski pozisyonu kapat ve yeni pozisyona geç
        const idx = this.positions.findIndex(p => p.id === existing.id);
        if (idx !== -1) {
          this.closePosition(idx, `🔄 FORMASYON BOZULDU (Ters Sinyal: ${side} Açıldı)`);
        }
      }
    }

    const newPos = {
      id: "POS-" + Date.now().toString().slice(-6),
      symbol: signal.symbol,
      side: side,
      size: size,
      entryPrice: entryPrice,
      markPrice: entryPrice,
      tp1: signal.tp1,
      sl: signal.sl,
      pnl: 0,
      pnlPercent: 0,
      timestamp: new Date().toLocaleTimeString('tr-TR')
    };

    this.balance -= allocationAmount;
    this.positions.push(newPos);
    this.saveToStorage();
    return newPos;
  }

  /**
   * Anlık Fiyat Değişimi ile Pozisyon PnL Güncelleme ve Otomatik TP/SL
   */
  updateMarkPrices(currentPrices) {
    let stateChanged = false;

    this.positions.forEach((pos, index) => {
      // Normalize symbol string to match ticker key (e.g. BTC/USDT -> BTCUSDT)
      const cleanSym = pos.symbol.replace('/', '').toUpperCase();
      const markPrice = currentPrices[cleanSym] || currentPrices[pos.symbol] || pos.entryPrice;
      pos.markPrice = markPrice;

      // PnL Calculation
      if (pos.side === "LONG") {
        pos.pnl = (markPrice - pos.entryPrice) * pos.size;
        pos.pnlPercent = ((markPrice - pos.entryPrice) / pos.entryPrice) * 100;
      } else {
        pos.pnl = (pos.entryPrice - markPrice) * pos.size;
        pos.pnlPercent = ((pos.entryPrice - markPrice) / pos.entryPrice) * 100;
      }

      // 🛡️ Erken Başabaş & Dinamik Kar Kilitleri (%0.5 Kar Görünce Risk Sıfırlanır)
      if (pos.side === "LONG") {
        if (pos.pnlPercent >= 0.5 && pos.sl < pos.entryPrice) {
          pos.sl = pos.entryPrice; // Risk Sıfırlandı (Başabaş Stop)
          stateChanged = true;
        } else if (pos.pnlPercent >= 1.2 && pos.sl < pos.entryPrice * 1.006) {
          pos.sl = parseFloat((pos.entryPrice * 1.006).toFixed(2)); // +0.6% Kar Kilitlendi
          stateChanged = true;
        } else if (pos.pnlPercent >= 2.2 && pos.sl < markPrice * 0.99) {
          pos.sl = parseFloat((markPrice * 0.99).toFixed(2)); // Dinamik İzleyen Stop (%1.0 Tampon)
          stateChanged = true;
        }
      } else { // SHORT
        if (pos.pnlPercent >= 0.5 && pos.sl > pos.entryPrice) {
          pos.sl = pos.entryPrice; // Risk Sıfırlandı (Başabaş Stop)
          stateChanged = true;
        } else if (pos.pnlPercent >= 1.2 && pos.sl > pos.entryPrice * 0.994) {
          pos.sl = parseFloat((pos.entryPrice * 0.994).toFixed(2)); // +0.6% Kar Kilitlendi
          stateChanged = true;
        } else if (pos.pnlPercent >= 2.2 && pos.sl > markPrice * 1.01) {
          pos.sl = parseFloat((markPrice * 1.01).toFixed(2)); // Dinamik İzleyen Stop (%1.0 Tampon)
          stateChanged = true;
        }
      }

      // Check Automated TP / SL Trigger
      if (pos.side === "LONG") {
        if (markPrice >= pos.tp1) {
          this.closePosition(index, "🎯 KAR AL (TP1) TETİKLENDİ");
          stateChanged = true;
        } else if (markPrice <= pos.sl) {
          const isTrailingSL = pos.sl > pos.entryPrice;
          this.closePosition(index, isTrailingSL ? "🎯 İZLEYEN STOP İLE KÂR KİLİTLENDİ" : "🛑 STOP LOSS (SL) TETİKLENDİ");
          stateChanged = true;
        }
      } else if (pos.side === "SHORT") {
        if (markPrice <= pos.tp1) {
          this.closePosition(index, "🎯 KAR AL (TP1) TETİKLENDİ");
          stateChanged = true;
        } else if (markPrice >= pos.sl) {
          const isTrailingSL = pos.sl < pos.entryPrice;
          this.closePosition(index, isTrailingSL ? "🎯 İZLEYEN STOP İLE KÂR KİLİTLENDİ" : "🛑 STOP LOSS (SL) TETİKLENDİ");
          stateChanged = true;
        }
      }
    });

    if (stateChanged) this.saveToStorage();
  }

  /**
   * Pozisyon Kapat
   */
  closePosition(index, reason = "Manuel Kapatıldı") {
    if (index < 0 || index >= this.positions.length) return;

    const pos = this.positions[index];
    const returnAmount = (pos.entryPrice * pos.size) + pos.pnl;
    this.balance += returnAmount;

    // Record History
    this.history.unshift({
      ...pos,
      closePrice: pos.markPrice,
      closeReason: reason,
      closeTimestamp: new Date().toLocaleTimeString('tr-TR')
    });

    // Keep history clean max 20
    if (this.history.length > 20) this.history.pop();

    this.positions.splice(index, 1);
    this.saveToStorage();
  }

  /**
   * Toplam Portföy Değeri (USDT Bakiye + Pozisyon Kar/Zararları)
   */
  getTotalEquity() {
    const unrealizedPnL = this.positions.reduce((acc, p) => acc + p.pnl, 0);
    return this.balance + (this.positions.reduce((acc, p) => acc + (p.entryPrice * p.size), 0)) + unrealizedPnL;
  }

  getWinRate() {
    if (this.history.length === 0) return 100;
    const wins = this.history.filter(h => h.pnl > 0).length;
    return Math.round((wins / this.history.length) * 100);
  }
}
