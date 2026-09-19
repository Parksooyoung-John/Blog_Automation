/* 예금·적금 이자계산기 — j2gblog
 * 티스토리 본문에는 <div id="jg-calc-deposit"></div> 와 이 파일을 부르는 script 태그만 넣는다.
 * 티스토리 새니타이저가 인라인 이벤트 속성과 span의 id를 지우므로, UI는 전부 JS가 그린다.
 */
(function () {
  var root = document.getElementById('jg-calc-deposit');
  if (!root) return;

  var TAX = { normal: 0.154, pref: 0.095, free: 0 };
  var S = {
    wrap: 'border:1px solid #e3e6ea;border-radius:12px;padding:18px;margin:20px 0;background:#fbfcfd;font-size:15px;line-height:1.6;',
    tab: 'flex:1;padding:10px;border:1px solid #d7dbe0;background:#fff;cursor:pointer;font-size:15px;font-weight:700;',
    tabOn: 'flex:1;padding:10px;border:1px solid #2c6ecb;background:#2c6ecb;color:#fff;cursor:pointer;font-size:15px;font-weight:700;',
    row: 'display:flex;align-items:center;gap:8px;margin:10px 0;flex-wrap:wrap;',
    label: 'min-width:92px;font-weight:600;color:#333;',
    input: 'flex:1;min-width:120px;padding:9px 10px;border:1px solid #d7dbe0;border-radius:6px;font-size:15px;',
    sel: 'padding:9px 10px;border:1px solid #d7dbe0;border-radius:6px;font-size:15px;background:#fff;',
    out: 'margin-top:14px;padding:14px;background:#fff;border:1px solid #e3e6ea;border-radius:8px;',
    line: 'display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f1f3f5;',
    total: 'display:flex;justify-content:space-between;padding:10px 0 2px;font-weight:700;font-size:17px;color:#2c6ecb;',
    note: 'margin-top:10px;font-size:12px;color:#888;'
  };
  var mode = 'deposit';

  function won(n) { return Math.round(n).toLocaleString('ko-KR') + '원'; }
  function el(tag, style, html) {
    var e = document.createElement(tag);
    if (style) e.setAttribute('style', style);
    if (html != null) e.innerHTML = html;
    return e;
  }
  function field(labelText, node) {
    var r = el('div', S.row);
    r.appendChild(el('span', S.label, labelText));
    r.appendChild(node);
    return r;
  }
  function num(id, val) {
    var i = el('input', S.input);
    i.type = 'number'; i.id = id; i.value = val; i.min = '0';
    return i;
  }
  function sel(id, opts) {
    var s = el('select', S.sel); s.id = id;
    opts.forEach(function (o) {
      var op = document.createElement('option');
      op.value = o[0]; op.textContent = o[1];
      s.appendChild(op);
    });
    return s;
  }

  /* 예금: 목돈을 한 번에 맡긴다
   *   단리   이자 = 원금 × r × (개월/12)
   *   월복리 이자 = 원금 × ((1 + r/12)^개월 − 1)
   * 적금: 매월 넣는다
   *   단리   이자 = 월납입 × (r/12) × n(n+1)/2   (첫 회차가 n개월, 마지막 회차가 1개월치 이자)
   *   월복리 각 회차를 남은 개월수만큼 복리 적용해 합산
   */
  function calc(mode, amount, rate, months, method, taxKey) {
    var r = rate / 100, i = r / 12, principal, gross;
    if (mode === 'deposit') {
      principal = amount;
      gross = method === 'compound' ? amount * (Math.pow(1 + i, months) - 1) : amount * r * (months / 12);
    } else {
      principal = amount * months;
      if (method === 'compound') {
        var fv = 0;
        for (var k = 1; k <= months; k++) fv += amount * Math.pow(1 + i, months - k + 1);
        gross = fv - principal;
      } else {
        gross = amount * i * (months * (months + 1) / 2);
      }
    }
    var tax = gross * TAX[taxKey];
    return { principal: principal, gross: gross, tax: tax, net: gross - tax, total: principal + gross - tax };
  }

  function render() {
    root.innerHTML = '';
    var box = el('div', S.wrap);

    var tabs = el('div', 'display:flex;gap:6px;margin-bottom:14px;');
    var tabD = el('button', mode === 'deposit' ? S.tabOn : S.tab, '예금 (목돈)');
    var tabS = el('button', mode === 'saving' ? S.tabOn : S.tab, '적금 (매월)');
    tabD.type = 'button'; tabS.type = 'button';
    tabD.addEventListener('click', function () { mode = 'deposit'; render(); });
    tabS.addEventListener('click', function () { mode = 'saving'; render(); });
    tabs.appendChild(tabD); tabs.appendChild(tabS);
    box.appendChild(tabs);

    var isDep = mode === 'deposit';
    box.appendChild(field(isDep ? '예치금액' : '월 납입액', num('jg-amt', isDep ? 10000000 : 500000)));
    box.appendChild(field('연이율(%)', num('jg-rate', 3.5)));
    box.appendChild(field('기간(개월)', num('jg-months', 12)));
    box.appendChild(field('이자방식', sel('jg-method', [['simple', '단리'], ['compound', '월복리']])));
    box.appendChild(field('과세', sel('jg-tax', [
      ['normal', '일반과세 15.4%'], ['pref', '세금우대 9.5%'], ['free', '비과세 0%']
    ])));

    var out = el('div', S.out);
    out.id = 'jg-out';
    box.appendChild(out);
    box.appendChild(el('p', S.note,
      '단리·월복리 공식으로 계산한 참고용 결과입니다. 실제 지급액은 금융회사의 이자 계산 방식과 이자 지급 시기, 우대금리 조건에 따라 달라질 수 있습니다.'));
    root.appendChild(box);

    ['jg-amt', 'jg-rate', 'jg-months', 'jg-method', 'jg-tax'].forEach(function (id) {
      var e = document.getElementById(id);
      e.addEventListener('input', update);
      e.addEventListener('change', update);
    });
    update();
  }

  function update() {
    var amount = Number(document.getElementById('jg-amt').value || 0);
    var rate = Number(document.getElementById('jg-rate').value || 0);
    var months = Math.max(1, Math.round(Number(document.getElementById('jg-months').value || 1)));
    var method = document.getElementById('jg-method').value;
    var taxKey = document.getElementById('jg-tax').value;
    var r = calc(mode, amount, rate, months, method, taxKey);
    var label = mode === 'deposit' ? '예치원금' : '납입원금 합계';
    document.getElementById('jg-out').innerHTML =
      '<div style="' + S.line + '"><span>' + label + '</span><strong>' + won(r.principal) + '</strong></div>' +
      '<div style="' + S.line + '"><span>세전 이자</span><strong>' + won(r.gross) + '</strong></div>' +
      '<div style="' + S.line + '"><span>이자과세</span><strong>-' + won(r.tax) + '</strong></div>' +
      '<div style="' + S.line + '"><span>세후 이자</span><strong>' + won(r.net) + '</strong></div>' +
      '<div style="' + S.total + '"><span>만기 수령액</span><span>' + won(r.total) + '</span></div>';
  }

  render();
  window.jgCalcDeposit = calc; // 자체 검증용
})();
