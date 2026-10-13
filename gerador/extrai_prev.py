"""Lê o PDF da programação de preventiva (PROJ. PREVENTIVA ...) e devolve as semanas do mês.

Uso: python3 extrai_prev.py PREVENTIVA.pdf saida.json
Cada item: [prefixo, modelo, horimetro, seq, os, indiceDia, realizada, caixa, obs, itemFaltante]
"""
import datetime
import json
import re
import sys

import pdfplumber

WD = ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB']


def ler(src):
    weeks, cur = [], None
    with pdfplumber.open(src) as p:
        for pg in p.pages:
            words = pg.extract_words()
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
                lo, hi = cx[0] - 30, cx[-1] + 30
                pf = ws[0]['text'] + ' ' + ws[1]['text']
                lt = [w['text'] for w in ws[2:] if (w['x0'] + w['x1']) / 2 < lo]
                rt = [w['text'] for w in ws if (w['x0'] + w['x1']) / 2 > hi]
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
                    c = (cand[0]['x0'] + cand[0]['x1']) / 2
                    dia = min(range(len(cx)), key=lambda i: abs(cx[i] - c))
                    feita = 1 if cand[0]['text'] == 'V' else 0
                elif re.search(r'(EXECUTADO|REALIZADO) EM', obs):
                    feita = 1
                cur['itens'].append([pf, mod, hor, seq, os_, dia, feita, caixa, obs, ' '.join(falta)])
    res = {'semanas': []}
    for w in weeks:
        d = w['dias']
        if not d:
            continue
        res['semanas'].append({'n': w['n'], 'titulo': '%s SEMANA %d · %s A %s' % (w['mes'], w['n'], d[0][1][:2], d[-1][1]),
                               'dias': d, 'itens': w['itens']})
    return res


if __name__ == '__main__':
    r = ler(sys.argv[1])
    json.dump(r, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for s in r['semanas']:
        print(s['titulo'], len(s['itens']), 'itens,', sum(i[6] for i in s['itens']), 'realizadas')
