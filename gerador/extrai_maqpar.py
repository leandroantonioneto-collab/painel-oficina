"""Lê o PDF MAQPAR (relatório de máquinas paradas do sistema) e devolve JSON.

Uso: python3 extrai_maqpar.py MAQPAR.pdf saida.json
"""
import json
import re
import sys

import pdfplumber

REG = re.compile(
    r'^([A-Z]{2,4} \d{4}) (\d+) (.+?) (\d+/ ?\d+) (\d\d/\d\d/\d{4}) (\d\d:\d\d) (\d\d/\d\d/\d{4}) (\d\d:\d\d) ?(.*)$'
)
PECA = re.compile(r'\bP[CÇ]\b|PE[CÇ]A|KIT|AGUARDANDO|N[AÃ]O FATURADO|FATURADO', re.I)


def ler(src):
    with pdfplumber.open(src) as p:
        texto = '\n'.join(pg.extract_text() or '' for pg in p.pages)
    linhas = [l.strip() for l in texto.split('\n') if l.strip()]
    data_rel = None
    for l in linhas[:3]:
        m = re.search(r'(\d\d)[./](\d\d)[./](\d{4})', l)
        if m:
            data_rel = '%s/%s/%s' % m.groups()
            break
    regs = []
    for l in linhas:
        m = REG.match(l)
        if m:
            regs.append(list(m.groups()))
        elif regs and not re.match(r'^(Equip|Dias|Parados|Modelo)', l):
            regs[-1][8] = (regs[-1][8] + ' ' + l).strip()
    out = []
    for g in regs:
        pf, dias, modelo, os_, ent_d, ent_h, prev_d, prev_h, obs = g
        sem_prev = (ent_d == prev_d and ent_h == prev_h)
        mo = re.match(r'(\d\d/\d\d)/\d{4} (\d\d:\d\d):\s*(.*)', obs)
        obs_dt, obs_txt = (mo.group(1) + ' ' + mo.group(2), mo.group(3)) if mo else ('', obs)
        out.append({
            'pf': pf, 'modelo': modelo.strip(), 'os': os_.replace(' ', ''),
            'entrada': ent_d[:6] + ent_d[8:], 'hora': ent_h,
            'previsao': None if sem_prev else prev_d[:5],
            'dias': int(dias), 'obsData': obs_dt, 'obs': obs_txt.strip(),
            'peca': 1 if PECA.search(obs_txt) else 0,
        })
    return {'dataRelatorio': data_rel, 'linhas': out}


if __name__ == '__main__':
    r = ler(sys.argv[1])
    json.dump(r, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(r['dataRelatorio'], len(r['linhas']), 'maquinas')
    for x in r['linhas']:
        print(' ', x['pf'], x['dias'], x['previsao'], 'peca' if x['peca'] else '', '|', x['obs'][:70])
