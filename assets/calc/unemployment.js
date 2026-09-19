/* 실업급여(구직급여) 계산기 — j2gblog
 * 본문에는 <div id="jg-calc-unemp"></div> 와 이 파일을 부르는 script 태그만 넣는다.
 * 티스토리 새니타이저가 인라인 이벤트와 span의 id를 지우므로 UI는 전부 JS가 그린다.
 *
 * 2026년 기준값 (고용보험법 시행령 개정, 2026-01-01 시행)
 *   구직급여일액 = 이직 전 3개월 평균임금의 60%
 *   상한 68,100원 (임금일액 상한 113,500원 × 60%)
 *   하한 66,048원 (2026년 최저임금 10,320원 × 80% × 8시간)
 *   소정급여일수: 고용보험법 제50조 별표1
 */
(function () {
  var root = document.getElementById('jg-calc-unemp');
  if (!root) return;

  var CAP = 68100, FLOOR = 66048, RATE = 0.6, DAYS3M = 91;
  // [1년 미만, 1~3년, 3~5년, 5~10년, 10년 이상]
  var DAYS = { under50: [120, 150, 180, 210, 240], over50: [120, 180, 210, 240, 270] };
  var TERMS = [
    ['0', '1년 미만'], ['1', '1년 이상 3년 미만'], ['2', '3년 이상 5년 미만'],
    ['3', '5년 이상 10년 미만'], ['4', '10년 이상']
  ];
  var S = {
    wrap: 'border:1px solid #e3e6ea;border-radius:12px;padding:18px;margin:20px 0;background:#fbfcfd;font-size:15px;line-height:1.6;',
    row: 'display:flex;align-items:center;gap:8px;margin:10px 0;flex-wrap:wrap;',
    label: 'min-width:150px;font-weight:600;color:#333;',
    input: 'flex:1;min-width:120px;padding:9px 10px;border:1px solid #d7dbe0;border-radius:6px;font-size:15px;',
    sel: 'flex:1;min-width:140px;padding:9px 10px;border:1px solid #d7dbe0;border-radius:6px;font-size:15px;background:#fff;',
    out: 'margin-top:14px;padding:14px;background:#fff;border:1px solid #e3e6ea;border-radius:8px;',
    line: 'display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f1f3f5;',
    total: 'display:flex;justify-content:space-between;padding:10px 0 2px;font-weight:700;font-size:17px;color:#2c6ecb;',
    badge: 'display:inline-block;margin-top:10px;padding:6px 10px;border-radius:6px;font-size:13px;background:#eef4ff;color:#2c6ecb;',
    note: 'margin-top:10px;font-size:12px;color:#888;'
  };

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
  function sel(id, opts) {
    var s = el('select', S.sel); s.id = id;
    opts.forEach(function (o) {
      var op = document.createElement('option');
      op.value = o[0]; op.textContent = o[1];
      s.appendChild(op);
    });
    return s;
  }

  /* monthlyPay: 이직 전 3개월 평균 월 세전 급여
   * ageGroup: 'under50' | 'over50'   termIdx: 0~4
   * 평균임금은 3개월 총액을 그 기간의 총 일수로 나눈다(여기서는 91일 기준).
   */
  function calc(monthlyPay, ageGroup, termIdx) {
    var daily = monthlyPay * 3 / DAYS3M;
    var raw = daily * RATE;
    var capped = raw > CAP, floored = raw < FLOOR;
    var benefit = Math.min(Math.max(raw, FLOOR), CAP);
    var days = DAYS[ageGroup][termIdx];
    return {
      dailyWage: daily, raw: raw, benefit: benefit, days: days,
      total: benefit * days, monthly: benefit * 30,
      capped: capped, floored: floored
    };
  }

  function render() {
    root.innerHTML = '';
    var box = el('div', S.wrap);
    var pay = el('input', S.input);
    pay.type = 'number'; pay.id = 'jg-pay'; pay.value = 3000000; pay.min = '0'; pay.step = '100000';
    box.appendChild(field('월 평균 세전 급여', pay));
    box.appendChild(field('이직일 기준 나이', sel('jg-age', [
      ['under50', '50세 미만'], ['over50', '50세 이상 또는 장애인']
    ])));
    box.appendChild(field('고용보험 가입기간', sel('jg-term', TERMS)));

    var out = el('div', S.out); out.id = 'jg-unemp-out';
    box.appendChild(out);
    box.appendChild(el('p', S.note,
      '이직 전 3개월 평균임금을 91일 기준으로 환산한 참고값입니다. 실제 지급액은 고용센터가 산정한 평균임금과 수급자격 인정 여부에 따라 달라지며, 대기기간 7일은 지급되지 않습니다.'));
    root.appendChild(box);

    ['jg-pay', 'jg-age', 'jg-term'].forEach(function (id) {
      var e = document.getElementById(id);
      e.addEventListener('input', update);
      e.addEventListener('change', update);
    });
    update();
  }

  function update() {
    var pay = Number(document.getElementById('jg-pay').value || 0);
    var age = document.getElementById('jg-age').value;
    var term = Number(document.getElementById('jg-term').value);
    var r = calc(pay, age, term);
    var badge = r.capped
      ? '상한액이 적용됐습니다. 급여가 더 높아도 1일 ' + won(CAP) + '을 넘지 않습니다.'
      : (r.floored
        ? '하한액이 적용됐습니다. 급여가 더 낮아도 1일 ' + won(FLOOR) + '은 보장됩니다.'
        : '상·하한 사이 구간이라 평균임금의 60%가 그대로 적용됩니다.');
    document.getElementById('jg-unemp-out').innerHTML =
      '<div style="' + S.line + '"><span>1일 평균임금</span><strong>' + won(r.dailyWage) + '</strong></div>' +
      '<div style="' + S.line + '"><span>평균임금의 60%</span><strong>' + won(r.raw) + '</strong></div>' +
      '<div style="' + S.line + '"><span>1일 구직급여</span><strong>' + won(r.benefit) + '</strong></div>' +
      '<div style="' + S.line + '"><span>소정급여일수</span><strong>' + r.days + '일</strong></div>' +
      '<div style="' + S.line + '"><span>30일 기준 월 환산</span><strong>' + won(r.monthly) + '</strong></div>' +
      '<div style="' + S.total + '"><span>총 예상 수령액</span><span>' + won(r.total) + '</span></div>' +
      '<div style="' + S.badge + '">' + badge + '</div>';
  }

  render();
  window.jgCalcUnemp = calc; // 자체 검증용
})();
