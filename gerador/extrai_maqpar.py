"""Lê o PDF MAQPAR (relatório de máquinas paradas do sistema) e devolve JSON.

Funciona com o formato antigo (sem Prognóstico) e o novo (com "Tipo Doc." e "Prognóstico").
A coluna de observação começa na data "dd/mm/aaaa hh:mm:" de cada linha; o que fica à
esquerda dela é o prognóstico.
Uso: python3 extrai_maqpar.py MAQPAR.pdf saida.json
"""
import json
import re
import sys

import pdfplumber

INICIO = re.compile(
    r'^([A-Z]{2,4} \d{4}) (\d+) (.+?) (\d+/ ?\d+) (?:O\.S\. )?(\d\d/\d\d/\d{4}) (\d\d:\d\d) (\d\d/\d\d/\d{4}) (?:(\S*[A-Za-zÀ-ú]\S*) )?(\d\d:\d\d)\b'
)
PECA = re.compile(r'\bP[CÇ]\b|PE[CÇ]AS?\b|KIT|AGUARDANDO|FATURADO|EMBARC', re.I)
DATA = re.compile(r'\d\d/\d\d/\d{4}')
HORA = re.compile(r'\d\d:\d\d:')
CABEC = re.compile(r'^(Equip|Dias|Parados|\d\d\.\d\d\.\d{4})')


def _linhas(pg):
    # use_text_flow: textos sobrepostos na mesma altura (ex.: prognóstico em 2 linhas
    # passando por cima da hora da previsão) não se misturam letra a letra.
    ws = sorted(pg.extract_words(use_text_flow=True), key=lambda w: (round(w['top']), w['x0']))
    out = []
    for w in ws:
        if out and abs(out[-1]['top'] - w['top']) < 3:
            out[-1]['ws'].append(w)
        else:
            out.append({'top': w['top'], 'ws': [w]})
    for L in out:
        L['ws'].sort(key=lambda w: w['x0'])
        L['txt'] = ' '.join(w['text'] for w in L['ws'])
    return out


def _poe(reg, w):
    if reg['x'] is None or w['x0'] >= reg['x'] - 4:
        reg['obs'].append(w['text'])
    else:
        reg['prog'].append(w['text'])


def ler(src):
    regs, data_rel = [], None
    with pdfplumber.open(src) as p:
        for pg in p.pages:
            for L in _linhas(pg):
                m = INICIO.match(L['txt'])
                if data_rel is None and not m:
                    md = re.search(r'(\d\d)[./](\d\d)[./](\d{4})', L['txt'])
                    if md:
                        data_rel = '%s/%s/%s' % md.groups()
                if m:
                    resto = L['ws'][len(m.group(0).split(' ')):]
                    x = None
                    for i, w in enumerate(resto):
                        if DATA.fullmatch(w['text']) and i + 1 < len(resto) and HORA.fullmatch(resto[i + 1]['text']):
                            x = w['x0']
                            break
                    g = list(m.groups())
                    intruso = g.pop(7)  # palavra do prognóstico que caiu antes da hora da previsão
                    regs.append({'g': g, 'prog': [intruso] if intruso else [], 'obs': [], 'x': x})
                    for w in resto:
                        _poe(regs[-1], w)
                elif regs and not CABEC.match(L['txt']):
                    for w in L['ws']:
                        _poe(regs[-1], w)
    out = []
    for r in regs:
        pf, dias, modelo, os_, ent_d, ent_h, prev_d, prev_h = r['g']
        obs = ' '.join(r['obs']).strip()
        mo = re.match(r'(\d\d/\d\d)/\d{4} (\d\d:\d\d):\s*', obs)
        obs_dt, obs_txt = (mo.group(1) + ' ' + mo.group(2), obs[mo.end():]) if mo else ('', obs)
        prog = re.sub(r'\s*;\s*$', '', ' '.join(r['prog']).strip()).replace(' ;', ';')
        out.append({
            'pf': pf, 'modelo': modelo.strip(), 'os': os_.replace(' ', ''),
            'entrada': ent_d[:6] + ent_d[8:], 'hora': ent_h,
            'previsao': None if (ent_d == prev_d and ent_h == prev_h) else prev_d[:5],
            'dias': int(dias), 'prognostico': prog, 'obsData': obs_dt, 'obs': obs_txt.strip(),
            'peca': 1 if PECA.search(obs_txt + ' ' + prog) else 0,
        })
    return {'dataRelatorio': data_rel, 'linhas': out}


if __name__ == '__main__':
    r = ler(sys.argv[1])
    json.dump(r, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(r['dataRelatorio'], len(r['linhas']), 'maquinas')
    for x in r['linhas']:
        print(' ', x['pf'], x['dias'], x['previsao'], 'PECA' if x['peca'] else '', '| P:', x['prognostico'][:50], '| O:', x['obsData'], x['obs'][:55])
