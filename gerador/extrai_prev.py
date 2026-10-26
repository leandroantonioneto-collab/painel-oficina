"""Lê o PDF da programação de preventiva (PROJ. PREVENTIVA ...) e devolve as semanas do mês.

Uso: python3 extrai_prev.py PREVENTIVA.pdf saida.json
Cada item: [prefixo, modelo, horimetro, seq, os, indiceDia, realizada, caixa, obs, itemFaltante(, ultimoAbastecimento)]
O último elemento só existe quando o PDF tem a coluna 'ULTIMO ABASTECIMENTO' (formato a partir de 23/10/2026).
"""
import datetime
import json
import re
import sys

import pdfplumber

WD = ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB']


_DT = re.compile(r'\d\d/\d\d/\d{4}')


def _palavras(pg):
    """extract_words, separando datas que vêm coladas numa só palavra
    (ex.: 'ABASTECIME25/10/202626/10/2026...' no PDF de 26/10)."""
    out = []
    for w in pg.extract_words(return_chars=True):
        t, ch = w['text'], w.get('chars') or []
        ms = list(_DT.finditer(t))
        if len(ch) != len(t) or not ms or (len(ms) == 1 and ms[0].span() == (0, len(t))):
            w.pop('chars', None)
            out.append(w)
            continue
        cuts, pos = [], 0
        for m in ms:
            if m.start() > pos:
                cuts.append((pos, m.start()))
            cuts.append(m.span())
            pos = m.end()
        if pos < len(t):
            cuts.append((pos, len(t)))
        for a, b in cuts:
            cs = ch[a:b]
            out.append({'text': t[a:b], 'x0': min(c['x0'] for c in cs), 'x1': max(c['x1'] for c in cs),
                        'top': min(c['top'] for c in cs), 'bottom': max(c['bottom'] for c in cs)})
    return out


def ler(src):
    weeks, cur = [], None
    with pdfplumber.open(src) as p:
        for pg in p.pages:
            words = _palavras(pg)
            lines = []
            for w in sorted(words, key=lambda w: (round(w['top']), w['x0'])):
                if lines and abs(lines[-1]['top'] - w['top']) < 3:
                    lines[-1]['ws'].append(w)
                else:
                    lines.append({'top': w['top'], 'ws': [w]})
            marks = [w for w in words if w['text'] in ('X', 'V')]
            for L in lines:
                ws = sorted(L['ws'], key=lambda w: w['x0'])
                txt = ' '.join(w['text'] for w in ws)
                m = re.search(r'([A-ZÇ]+) - SEMANA (\d)', txt)
                if m:
                    cur = {'n': int(m.group(2)), 'mes': m.group(1), 'cols': None, 'dias': [], 'itens': []}
                    weeks.append(cur)
                    continue
                ds = [w for w in ws if re.fullmatch(r'\d\d/\d\d/\d{4}', w['text'])]
                if 'PREFIXO' in txt and ds and cur:
                    cur['cols'] = [(w['x0'] + w['x1']) / 2 for w in ds]
                    ex = [w for w in ws if w['text'] == 'EXECUÇÃO']
                    sq = [w for w in ws if w['text'] == 'SEQ']
                    cur['band'] = (ex[0]['x0'] - 8, ex[0]['x1'] + 8, sq[0]['x0'] - 4) if ex and sq else None
                    cur['dias'] = []
                    for w in ds:
                        d = datetime.date(int(w['text'][6:]), int(w['text'][3:5]), int(w['text'][:2]))
                        cur['dias'].append([WD[(d.weekday() + 1) % 7], w['text'][:5]])
                    continue
                if not cur or not cur['cols']:
                    continue
                if not (len(ws) >= 2 and re.fullmatch(r'[A-Z]{2,4}', ws[0]['text']) and re.fullmatch(r'\d{4}', ws[1]['text']) and ws[0]['x0'] < 60):
                    continue
                cx = cur['cols']
                pc = cx[1] - cx[0] if len(cx) > 1 else 99
                mg = 30 if pc >= 30 else pc * 0.6  # PDF retrato (26/10) tem colunas estreitas
                lo, hi = cx[0] - mg, cx[-1] + mg
                pf = ws[0]['text'] + ' ' + ws[1]['text']
                ctr = lambda w: (w['x0'] + w['x1']) / 2
                lw = [w for w in ws[2:] if ctr(w) < lo]
                lt = [w['text'] for w in lw]
                rt = [w['text'] for w in ws if ctr(w) > hi]
                ab = None
                if cur.get('band'):
                    # separa pelas colunas do cabeçalho: MODELO | HORIMETRO MANUTENÇÃO | ULTIMO ABASTECIMENTO | SEQ OS
                    h0, h1, s0 = cur['band']
                    mod = ' '.join(w['text'] for w in lw if ctr(w) < h0)
                    hor = ' '.join(w['text'] for w in lw if h0 <= ctr(w) <= h1)
                    abt = ' '.join(w['text'] for w in lw if h1 < ctr(w) < s0)
                    dir_ = [w['text'] for w in lw if ctr(w) >= s0]
                    os_ = next((t for t in dir_ if re.fullmatch(r'00\d{4}', t)), '')
                    seq = ' '.join(t for t in dir_ if re.fullmatch(r'\d|ou', t))
                    if not abt:
                        # formato de 26/10: ULTIMO ABASTECIMENTO vem depois de SEQ/OS
                        resto = [t for t in dir_ if not re.fullmatch(r'\d|ou', t) and t != os_]
                        abt = resto[0] if len(resto) == 1 else ''
                    if re.fullmatch(r'[\d.]+', abt):
                        ab = int(abt.replace('.', ''))
                else:
                    os_ = lt.pop() if lt and re.fullmatch(r'00\d{4}', lt[-1]) else ''
                    mm = re.match(r'(.*?)\s+(\S+)\s+(\d(?: ou \d)?)$', ' '.join(lt))
                    mod, hor, seq = (mm.group(1), mm.group(2), mm.group(3)) if mm else (' '.join(lt), '', '')
                if re.fullmatch(r'\d\d/\d\d/\d{4}', hor):
                    hor = ''
                caixa, obs, falta = '', rt, []
                for i, t in enumerate(rt):
                    if t in ('INTEGRAL', 'IINTEGRAL', 'PARCIAL'):
                        caixa = 'Parcial' if t == 'PARCIAL' else 'Integral'
                        obs, falta = rt[:i], rt[i + 1:]
                        break
                obs = ' '.join(obs)
                cand = [k for k in marks if abs(k['top'] - L['top']) < 6 and lo < (k['x0'] + k['x1']) / 2 < hi]
                dia, feita = None, 0
                if cand:
                    k = min(cand, key=lambda k: abs(k['top'] - L['top']))  # linhas apertadas: pega a marca mais próxima
                    c = (k['x0'] + k['x1']) / 2
                    dia = min(range(len(cx)), key=lambda i: abs(cx[i] - c))
                    feita = 1 if k['text'] == 'V' else 0
                elif re.search(r'(EXECUTADO|REALIZADO) EM', obs):
                    feita = 1
                cur['itens'].append([pf, mod, hor, seq, os_, dia, feita, caixa, obs, ' '.join(falta), ab])
    for w in weeks:
        w['abast'] = any(it[10] is not None for it in w['itens'])
        if not w['abast']:
            for it in w['itens']:
                it.pop()
    res = {'semanas': []}
    for w in weeks:
        d = w['dias']
        if not d:
            continue
        res['semanas'].append({'n': w['n'], 'titulo': '%s SEMANA %d · %s A %s' % (w['mes'], w['n'], d[0][1][:2], d[-1][1]),
                               'dias': d, 'itens': w['itens'], 'abast': w['abast']})
    return res


if __name__ == '__main__':
    r = ler(sys.argv[1])
    json.dump(r, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for s in r['semanas']:
        print(s['titulo'], len(s['itens']), 'itens,', sum(i[6] for i in s['itens']), 'realizadas')


def ler_horimetros(src):
    """Lê a camada 'ULTIMO HORIMETRO' (fonte Helvetica) que vem sobreposta no PDF atualizado.

    Devolve {numero_semana: {'data': 'dd/mm', 'valores': [int|None, ...]}} na ordem das linhas.
    """
    res = {}
    with pdfplumber.open(src) as p:
        for pg in p.pages:
            camada = pg.filter(lambda o: o.get('object_type') != 'char' or o.get('fontname', '').startswith('Helvetica'))
            ws = camada.extract_words()
            txt = ' '.join(w['text'] for w in ws)
            ms = re.search(r'SEMANA (\d).*?ATUALIZADOS EM (\d\d/\d\d)', txt)
            if not ms or 'HORIMETRO' not in txt:
                continue
            cab = [w for w in ws if w['text'] == 'HORIMETRO']
            if not cab:
                continue
            x0, topo = cab[0]['x0'] - 15, cab[0]['top']
            linhas = {}
            for w in ws:
                if w['top'] > topo + 4 and x0 <= w['x0'] <= x0 + 50 and not w['text'].startswith('Ultima'):
                    k = round(w['top'])
                    linhas.setdefault(k, []).append(w['text'])
            vals = []
            for k in sorted(linhas):
                t = ' '.join(linhas[k])
                if 'Sem' in t:
                    vals.append(None)
                elif re.fullmatch(r'[\d.]+', t):
                    vals.append(int(t.replace('.', '')))
            res[int(ms.group(1))] = {'data': ms.group(2), 'valores': vals}
    return res
