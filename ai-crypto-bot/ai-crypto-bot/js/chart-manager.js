/**
 * Grafik Yöneticisi (Canvas HTML5 / Chart Renderer v5.0)
 * - Canlı Fiyat & Hacim Çizgileri
 * - Trend Kanalı Çizimi (Yükselen / Düşen Kanal Üst ve Alt Çizgileri)
 * - Grid Izgara Kanalı Çizimi (Grid Alt/Üst Sınırları & Alım/Satım Kademeleri)
 * - Formasyon Çizimleri (W Dip, M Tepe, Boğa Bayrağı Kırılım Çizgileri)
 * - Destek & Direnç, TP1/TP2/TP3 ve Stop-Loss Seviyeleri
 * - YZ Gelecek Fiyat Tahmin Eğrisi
 * - HD Analiz Görseli İndirme Desteği
 */

export class ChartManager {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
    this.resizeCanvas();
    window.addEventListener('resize', () => this.resizeCanvas());
  }

  resizeCanvas() {
    if (!this.canvas) return;
    const parent = this.canvas.parentElement;
    if (parent) {
      this.canvas.width = parent.clientWidth;
      this.canvas.height = parent.clientHeight || 420;
    }
  }

  renderChart(priceData, indicators, predictionCurve = [], options = {}) {
    if (!this.ctx || !priceData || priceData.length === 0) return;

    const ctx = this.ctx;
    const width = this.canvas.width;
    const height = this.canvas.height;

    // Canvas Clear
    ctx.clearRect(0, 0, width, height);

    // Padding
    const padLeft = 15;
    const padRight = 85;
    const padTop = 35;
    const padBottom = 45;

    const chartWidth = width - padLeft - padRight;
    const chartHeight = height - padTop - padBottom;

    // Total points including prediction
    const historyCount = priceData.length;
    const predCount = predictionCurve.length > 1 ? predictionCurve.length - 1 : 0;
    const totalPoints = historyCount + predCount;

    // Min & Max prices for scaling
    let allPrices = [...priceData];
    if (predictionCurve.length > 0) {
      allPrices = allPrices.concat(predictionCurve);
    }
    if (indicators) {
      if (indicators.bollingerUpper) allPrices.push(indicators.bollingerUpper);
      if (indicators.bollingerLower) allPrices.push(indicators.bollingerLower);
      if (indicators.supportLevel) allPrices.push(indicators.supportLevel);
      if (indicators.resistanceLevel) allPrices.push(indicators.resistanceLevel);
    }
    if (options.signal) {
      if (options.signal.tp1) allPrices.push(options.signal.tp1);
      if (options.signal.tp2) allPrices.push(options.signal.tp2);
      if (options.signal.sl) allPrices.push(options.signal.sl);
    }
    if (options.gridBot) {
      if (options.gridBot.lowerPrice) allPrices.push(options.gridBot.lowerPrice);
      if (options.gridBot.upperPrice) allPrices.push(options.gridBot.upperPrice);
    }

    const minPrice = Math.min(...allPrices) * 0.994;
    const maxPrice = Math.max(...allPrices) * 1.006;
    const priceRange = maxPrice - minPrice || 1;

    const getX = (index) => padLeft + (index / (totalPoints - 1)) * chartWidth;
    const getY = (price) => height - padBottom - ((price - minPrice) / priceRange) * chartHeight;

    // 1. Grid Background Lines & Price Labels
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#6b7280';
    ctx.font = '11px JetBrains Mono, monospace';

    const gridLines = 6;
    for (let i = 0; i <= gridLines; i++) {
      const p = minPrice + (i / gridLines) * priceRange;
      const y = getY(p);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();

      // Right Y-Axis Price Label
      ctx.fillText(`$${p.toFixed(2)}`, width - padRight + 8, y + 4);
    }

    // 2. Bollinger Band Shadow Area
    if (indicators && indicators.bollingerUpper && indicators.bollingerLower) {
      const upperY = getY(indicators.bollingerUpper);
      const lowerY = getY(indicators.bollingerLower);
      ctx.fillStyle = 'rgba(0, 242, 254, 0.04)';
      ctx.fillRect(padLeft, upperY, chartWidth, Math.max(0, lowerY - upperY));

      // Bollinger Upper/Lower lines
      ctx.strokeStyle = 'rgba(0, 242, 254, 0.25)';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(padLeft, upperY);
      ctx.lineTo(width - padRight, upperY);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(padLeft, lowerY);
      ctx.lineTo(width - padRight, lowerY);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 3. 📐 TREND KANAL ÇİZİMİ (Trend Channel Lines & Translucent Corridor)
    this.drawTrendChannel(ctx, priceData, getX, getY, padLeft, width - padRight);

    // 4. 🌐 GRID BOT IZGARA KANAL ÇİZİMİ (Grid Boundaries & Orders)
    if (options.gridBot) {
      this.drawGridChannel(ctx, options.gridBot, getX, getY, padLeft, width - padRight);
    }

    // 5. 🎯 DESTEK, DİRENÇ & TP/SL SEVİYE ÇİZGİLERİ
    this.drawLevelsAndTPSL(ctx, indicators, options.signal, getX, getY, padLeft, width - padRight);

    // 6. Fiyat Geçmişi Çizgisi & Gradyan Dolgu
    ctx.beginPath();
    for (let i = 0; i < historyCount; i++) {
      const x = getX(i);
      const y = getY(priceData[i]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }

    const gradient = ctx.createLinearGradient(0, padTop, 0, height - padBottom);
    gradient.addColorStop(0, 'rgba(0, 242, 254, 0.25)');
    gradient.addColorStop(1, 'rgba(0, 242, 254, 0.0)');
    
    ctx.lineTo(getX(historyCount - 1), height - padBottom);
    ctx.lineTo(padLeft, height - padBottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Ana Fiyat Çizgisi
    ctx.beginPath();
    for (let i = 0; i < historyCount; i++) {
      const x = getX(i);
      const y = getY(priceData[i]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = '#00f2fe';
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // 7. 🧩 FORMASYON ÇİZİMLERİ (W Dip, M Tepe, Boğa Bayrağı Vurgusu)
    if (indicators && indicators.patterns) {
      this.drawFormations(ctx, priceData, indicators.patterns, getX, getY, historyCount);
    }

    // 8. Son Fiyat Noktası & Parlayan Nabız Metodu
    const lastX = getX(historyCount - 1);
    const lastY = getY(priceData[historyCount - 1]);

    ctx.beginPath();
    ctx.arc(lastX, lastY, 6, 0, Math.PI * 2);
    ctx.fillStyle = '#00f2fe';
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#ffffff';
    ctx.stroke();

    // 9. 🧠 YZ GELECEK TAHMİN EĞRİSİ (AI Prediction Line)
    if (predictionCurve && predictionCurve.length > 1) {
      const isBullish = predictionCurve[predictionCurve.length - 1] >= priceData[priceData.length - 1];
      const predColor = isBullish ? '#00e676' : '#ff1744';

      ctx.save();
      ctx.beginPath();
      ctx.setLineDash([5, 5]);

      for (let i = 0; i < predictionCurve.length; i++) {
        const x = getX(historyCount - 1 + i);
        const y = getY(predictionCurve[i]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }

      ctx.strokeStyle = predColor;
      ctx.lineWidth = 2.5;
      ctx.shadowColor = predColor;
      ctx.shadowBlur = 10;
      ctx.stroke();
      ctx.restore();

      // Tahmin Etiketi
      const endX = getX(totalPoints - 1);
      const endY = getY(predictionCurve[predictionCurve.length - 1]);
      
      ctx.fillStyle = isBullish ? 'rgba(0, 230, 118, 0.95)' : 'rgba(255, 23, 68, 0.95)';
      ctx.fillRect(endX - 54, endY - 12, 60, 22);
      ctx.fillStyle = '#000';
      ctx.font = 'bold 10px Outfit, sans-serif';
      ctx.fillText(isBullish ? 'YZ: YÜKSELİŞ' : 'YZ: DÜŞÜŞ', endX - 50, endY + 2);
    }
  }

  /**
   * 📐 Trend Kanalı Çizimi (Upper & Lower Trendlines & Shaded Corridor)
   */
  drawTrendChannel(ctx, prices, getX, getY, xStart, xEnd) {
    const len = prices.length;
    if (len < 10) return;

    // Tepe ve dip noktalarını hesapla
    let p1Index = Math.floor(len * 0.2);
    let p2Index = Math.floor(len * 0.8);
    
    let high1 = prices[p1Index], high2 = prices[p2Index];
    let low1 = prices[p1Index], low2 = prices[p2Index];

    for (let i = 0; i < Math.floor(len * 0.5); i++) {
      if (prices[i] > high1) { high1 = prices[i]; p1Index = i; }
      if (prices[i] < low1) { low1 = prices[i]; }
    }
    for (let i = Math.floor(len * 0.5); i < len; i++) {
      if (prices[i] > high2) { high2 = prices[i]; p2Index = i; }
      if (prices[i] < low2) { low2 = prices[i]; }
    }

    const x1 = getX(p1Index);
    const yHigh1 = getY(high1);
    const x2 = getX(p2Index);
    const yHigh2 = getY(high2);

    const slopeHigh = (yHigh2 - yHigh1) / (x2 - x1 || 1);
    const yUpperStart = yHigh1 + slopeHigh * (xStart - x1);
    const yUpperEnd = yHigh1 + slopeHigh * (xEnd - x1);

    const yLow1 = getY(low1);
    const yLow2 = getY(low2);
    const slopeLow = (yLow2 - yLow1) / (x2 - x1 || 1);
    const yLowerStart = yLow1 + slopeLow * (xStart - x1);
    const yLowerEnd = yLow1 + slopeLow * (xEnd - x1);

    // Kanal İçi Gölgelendirme (Translucent Shaded Area)
    ctx.fillStyle = 'rgba(124, 77, 255, 0.06)';
    ctx.beginPath();
    ctx.moveTo(xStart, yUpperStart);
    ctx.lineTo(xEnd, yUpperEnd);
    ctx.lineTo(xEnd, yLowerEnd);
    ctx.lineTo(xStart, yLowerStart);
    ctx.closePath();
    ctx.fill();

    // Üst Trend Çizgisi (Direnç Kanalı)
    ctx.strokeStyle = 'rgba(255, 64, 129, 0.7)';
    ctx.lineWidth = 1.8;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(xStart, yUpperStart);
    ctx.lineTo(xEnd, yUpperEnd);
    ctx.stroke();

    // Alt Trend Çizgisi (Destek Kanalı)
    ctx.strokeStyle = 'rgba(0, 230, 118, 0.7)';
    ctx.beginPath();
    ctx.moveTo(xStart, yLowerStart);
    ctx.lineTo(xEnd, yLowerEnd);
    ctx.stroke();
    ctx.setLineDash([]);

    // Kanal Etiketi
    ctx.fillStyle = '#b388ff';
    ctx.font = 'bold 9px Outfit, sans-serif';
    ctx.fillText('📐 TREND KANALI', xStart + 10, yUpperStart - 6);
  }

  /**
   * 🌐 Grid Bot Izgara Kanal Çizimi
   */
  drawGridChannel(ctx, gridBot, getX, getY, xStart, xEnd) {
    if (!gridBot || !gridBot.lowerPrice || !gridBot.upperPrice) return;

    const yLower = getY(gridBot.lowerPrice);
    const yUpper = getY(gridBot.upperPrice);

    // Grid Üst Bant Sınırı
    ctx.strokeStyle = '#ff4081';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 2]);
    ctx.beginPath();
    ctx.moveTo(xStart, yUpper);
    ctx.lineTo(xEnd, yUpper);
    ctx.stroke();

    ctx.fillStyle = '#ff4081';
    ctx.font = 'bold 10px JetBrains Mono, monospace';
    ctx.fillText(`GRID ÜST: $${gridBot.upperPrice}`, xEnd - 80, yUpper - 4);

    // Grid Alt Bant Sınırı
    ctx.strokeStyle = '#00e676';
    ctx.beginPath();
    ctx.moveTo(xStart, yLower);
    ctx.lineTo(xEnd, yLower);
    ctx.stroke();

    ctx.fillStyle = '#00e676';
    ctx.fillText(`GRID ALT: $${gridBot.lowerPrice}`, xEnd - 80, yLower + 12);

    // Ara Grid Izgara Çizgileri (Grids Mesh Lines)
    const gridCount = gridBot.grids || 5;
    const priceStep = (gridBot.upperPrice - gridBot.lowerPrice) / gridCount;

    ctx.strokeStyle = 'rgba(0, 242, 254, 0.2)';
    ctx.setLineDash([2, 4]);

    for (let i = 1; i < gridCount; i++) {
      const p = gridBot.lowerPrice + (i * priceStep);
      const yGrid = getY(p);

      ctx.beginPath();
      ctx.moveTo(xStart, yGrid);
      ctx.lineTo(xEnd, yGrid);
      ctx.stroke();

      ctx.fillStyle = 'rgba(0, 242, 254, 0.7)';
      ctx.font = '9px JetBrains Mono, monospace';
      ctx.fillText(`Grid #${i}: $${p.toFixed(2)}`, xStart + 10, yGrid - 3);
    }
    ctx.setLineDash([]);
  }

  /**
   * 🎯 Destek / Direnç ve TP / SL Seviye Çizgileri
   */
  drawLevelsAndTPSL(ctx, indicators, signal, getX, getY, xStart, xEnd) {
    if (indicators) {
      // Destek Seviyesi
      if (indicators.supportLevel) {
        const ySup = getY(indicators.supportLevel);
        ctx.strokeStyle = 'rgba(0, 230, 118, 0.8)';
        ctx.lineWidth = 1.2;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(xStart, ySup);
        ctx.lineTo(xEnd, ySup);
        ctx.stroke();

        ctx.fillStyle = '#00e676';
        ctx.font = 'bold 10px JetBrains Mono, monospace';
        ctx.fillText(`DESTEK: $${indicators.supportLevel}`, xStart + 10, ySup - 4);
      }

      // Direnç Seviyesi
      if (indicators.resistanceLevel) {
        const yRes = getY(indicators.resistanceLevel);
        ctx.strokeStyle = 'rgba(255, 23, 68, 0.8)';
        ctx.lineWidth = 1.2;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(xStart, yRes);
        ctx.lineTo(xEnd, yRes);
        ctx.stroke();

        ctx.fillStyle = '#ff1744';
        ctx.font = 'bold 10px JetBrains Mono, monospace';
        ctx.fillText(`DİRENÇ: $${indicators.resistanceLevel}`, xStart + 150, yRes - 4);
      }
    }

    if (signal) {
      ctx.setLineDash([3, 3]);

      // Stop-Loss
      if (signal.sl) {
        const ySL = getY(signal.sl);
        ctx.strokeStyle = '#ff1744';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(xStart, ySL);
        ctx.lineTo(xEnd, ySL);
        ctx.stroke();

        ctx.fillStyle = '#ff1744';
        ctx.font = 'bold 10px Outfit, sans-serif';
        ctx.fillText(`🛑 STOP LOSS: $${signal.sl}`, xEnd - 90, ySL - 4);
      }

      // Take Profits (TP1, TP2, TP3)
      const tpColors = ['#00e676', '#00b0ff', '#7c4dff'];
      [signal.tp1, signal.tp2, signal.tp3].forEach((tpVal, idx) => {
        if (!tpVal) return;
        const yTP = getY(tpVal);
        ctx.strokeStyle = tpColors[idx];
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(xStart, yTP);
        ctx.lineTo(xEnd, yTP);
        ctx.stroke();

        ctx.fillStyle = tpColors[idx];
        ctx.font = 'bold 10px Outfit, sans-serif';
        ctx.fillText(`🎯 TP${idx + 1}: $${tpVal}`, xEnd - 85, yTP - 4);
      });

      ctx.setLineDash([]);
    }
  }

  /**
   * 🧩 Grafik Formasyon Çizimleri (W Dip, M Tepe, Boğa Bayrağı)
   */
  drawFormations(ctx, prices, pattern, getX, getY, historyCount) {
    if (!pattern || !pattern.name) return;

    const len = prices.length;
    ctx.save();

    if (pattern.name.includes("W") || pattern.name.includes("İkili Dip")) {
      // W-Formasyonu Çizimi (Double Bottom)
      const idx1 = len - 15;
      const idx2 = len - 10;
      const idx3 = len - 5;
      const idx4 = len - 1;

      const p1 = { x: getX(idx1), y: getY(prices[idx1]) };
      const p2 = { x: getX(idx2), y: getY(prices[idx2]) };
      const p3 = { x: getX(idx3), y: getY(prices[idx3]) };
      const p4 = { x: getX(idx4), y: getY(prices[idx4]) };

      ctx.strokeStyle = '#00e676';
      ctx.lineWidth = 2.5;
      ctx.shadowColor = '#00e676';
      ctx.shadowBlur = 8;

      // W Hatlarını Çiz
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.lineTo(p3.x, p3.y);
      ctx.lineTo(p4.x, p4.y);
      ctx.stroke();

      // W Rozeti
      ctx.fillStyle = '#00e676';
      ctx.font = 'bold 11px Outfit, sans-serif';
      ctx.fillText(`🧩 FORMASYON: W-DİP (KIRILIM ONAYLI)`, p1.x, p2.y - 12);
    } 
    else if (pattern.name.includes("M") || pattern.name.includes("İkili Tepe")) {
      // M-Formasyonu Çizimi (Double Top)
      const idx1 = len - 15;
      const idx2 = len - 10;
      const idx3 = len - 5;
      const idx4 = len - 1;

      const p1 = { x: getX(idx1), y: getY(prices[idx1]) };
      const p2 = { x: getX(idx2), y: getY(prices[idx2]) };
      const p3 = { x: getX(idx3), y: getY(prices[idx3]) };
      const p4 = { x: getX(idx4), y: getY(prices[idx4]) };

      ctx.strokeStyle = '#ff1744';
      ctx.lineWidth = 2.5;
      ctx.shadowColor = '#ff1744';
      ctx.shadowBlur = 8;

      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.lineTo(p3.x, p3.y);
      ctx.lineTo(p4.x, p4.y);
      ctx.stroke();

      ctx.fillStyle = '#ff1744';
      ctx.font = 'bold 11px Outfit, sans-serif';
      ctx.fillText(`🧩 FORMASYON: M-TEPE (Direnç Reddi)`, p1.x, p1.y - 12);
    }
    else if (pattern.name.includes("Bayrak") || pattern.name.includes("Flag")) {
      // Boğa Bayrağı Çizimi (Bull Flag)
      const poleStart = { x: getX(len - 20), y: getY(prices[len - 20]) };
      const poleEnd = { x: getX(len - 10), y: getY(prices[len - 10]) };

      ctx.strokeStyle = '#00b0ff';
      ctx.lineWidth = 2.5;
      
      // Bayrak Direği
      ctx.beginPath();
      ctx.moveTo(poleStart.x, poleStart.y);
      ctx.lineTo(poleEnd.x, poleEnd.y);
      ctx.stroke();

      // Bayrak Kanalı
      ctx.strokeStyle = 'rgba(0, 176, 255, 0.7)';
      ctx.setLineDash([4, 2]);
      ctx.beginPath();
      ctx.moveTo(poleEnd.x, poleEnd.y);
      ctx.lineTo(getX(len - 1), getY(prices[len - 1]));
      ctx.stroke();

      ctx.fillStyle = '#00b0ff';
      ctx.font = 'bold 11px Outfit, sans-serif';
      ctx.fillText(`🚩 FORMASYON: BOĞA BAYRAĞI`, poleStart.x, poleEnd.y - 10);
    }

    ctx.restore();
  }

  /**
   * 📷 Grafiği Görsel (PNG Data URL) Olarak Dışa Aktar
   */
  exportChartAsImage() {
    if (!this.canvas) return null;
    return this.canvas.toDataURL('image/png');
  }
}

