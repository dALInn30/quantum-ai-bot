/**
 * Grafik Yöneticisi (Canvas HTML5 / Chart Renderer)
 * Canlı Fiyatlar, EMA 20/50, Bollinger ve YZ Gelecek Fiyat Tahmin Çizgisi
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
      this.canvas.height = parent.clientHeight || 380;
    }
  }

  renderChart(priceData, indicators, predictionCurve = []) {
    if (!this.ctx || !priceData || priceData.length === 0) return;

    const ctx = this.ctx;
    const width = this.canvas.width;
    const height = this.canvas.height;

    // Canvas Clear
    ctx.clearRect(0, 0, width, height);

    // Padding
    const padLeft = 10;
    const padRight = 60;
    const padTop = 30;
    const padBottom = 40;

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
    const minPrice = Math.min(...allPrices) * 0.995;
    const maxPrice = Math.max(...allPrices) * 1.005;
    const priceRange = maxPrice - minPrice || 1;

    const getX = (index) => padLeft + (index / (totalPoints - 1)) * chartWidth;
    const getY = (price) => height - padBottom - ((price - minPrice) / priceRange) * chartHeight;

    // 1. Grid Lines & Price Labels
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#6b7280';
    ctx.font = '11px JetBrains Mono, monospace';

    const gridLines = 5;
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

    // 2. Bollinger Band Shadow (Optional)
    if (indicators && indicators.bollingerUpper && indicators.bollingerLower) {
      const upperY = getY(indicators.bollingerUpper);
      const lowerY = getY(indicators.bollingerLower);
      ctx.fillStyle = 'rgba(0, 242, 254, 0.03)';
      ctx.fillRect(padLeft, upperY, chartWidth, Math.max(0, lowerY - upperY));
    }

    // 3. Price History Line & Area Gradient
    ctx.beginPath();
    for (let i = 0; i < historyCount; i++) {
      const x = getX(i);
      const y = getY(priceData[i]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }

    // Gradient Fill under price
    const gradient = ctx.createLinearGradient(0, padTop, 0, height - padBottom);
    gradient.addColorStop(0, 'rgba(0, 242, 254, 0.25)');
    gradient.addColorStop(1, 'rgba(0, 242, 254, 0.0)');
    
    ctx.lineTo(getX(historyCount - 1), height - padBottom);
    ctx.lineTo(padLeft, height - padBottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Draw main price line
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

    // 4. Current Price Dot & Glowing Pulse
    const lastX = getX(historyCount - 1);
    const lastY = getY(priceData[historyCount - 1]);

    ctx.beginPath();
    ctx.arc(lastX, lastY, 6, 0, Math.PI * 2);
    ctx.fillStyle = '#00f2fe';
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#ffffff';
    ctx.stroke();

    // 5. AI Future Prediction Curve (Dashed & Glowing Line)
    if (predictionCurve && predictionCurve.length > 1) {
      const isBullish = predictionCurve[predictionCurve.length - 1] >= priceData[priceData.length - 1];
      const predColor = isBullish ? '#00e676' : '#ff1744';

      ctx.save();
      ctx.beginPath();
      ctx.setLineDash([5, 5]); // Dashed style

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

      // Prediction Tag at end of curve
      const endX = getX(totalPoints - 1);
      const endY = getY(predictionCurve[predictionCurve.length - 1]);
      
      ctx.fillStyle = isBullish ? 'rgba(0, 230, 118, 0.9)' : 'rgba(255, 23, 68, 0.9)';
      ctx.fillRect(endX - 50, endY - 12, 55, 20);
      ctx.fillStyle = '#000';
      ctx.font = 'bold 10px Outfit, sans-serif';
      ctx.fillText(isBullish ? 'YZ: YÜKSELİŞ' : 'YZ: DÜŞÜŞ', endX - 46, endY + 2);
    }
  }
}
