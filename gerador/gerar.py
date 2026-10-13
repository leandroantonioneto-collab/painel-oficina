"""Gera o index.html do painel da oficina (protegido por senha).

Uso:
  python3 gerar.py --maqpar MAQPAR.pdf --preventiva PREVENTIVA.pdf --config config.json --saida ../index.html

config.json (fica no computador do usuário, NÃO no repositório):
  {"senha": "...", "frota": 195, "obra": "OBRA 421 – LUCAS/MT", "terceiros": "8/8 OK"}
"""
import argparse
import base64
import datetime
import json
import os
import pathlib
import re

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import extrai_maqpar
import extrai_prev

AQUI = pathlib.Path(__file__).parent


def ddmm(s):
    d, m = s.split('/')[:2]
    return int(m), int(d)


def infos_paradas(linhas, ref):
    """Monta a faixa 'Informações importantes' a partir do relatório."""
    infos = []
    if linhas:
        l = max(linhas, key=lambda x: x['dias'])
        curto = l['obs'] if len(l['obs']) <= 60 else l['obs'][:60].rsplit(' ', 1)[0] + '…'
        infos.append(['PARADA MAIS LONGA', 'red', '%s · %d dias · %s' % (l['pf'], l['dias'], curto.lower())])
    venc = [x['pf'] for x in linhas if x['previsao'] and ddmm(x['previsao']) < ref]
    infos.append(['%d PREVISÕES VENCIDAS · ATUALIZAR' % len(venc), 'red', ' · '.join(venc) or 'Nenhuma'])
    lib = []
    for x in linhas:
        for m in re.finditer(r'(LIBERAR|PREVIST[OA]|PREVIS[AÃ]O|ENTREGA|T[EÉ]CNICO)[^0-9]{0,40}?(\d\d/\d\d)', x['obs'], re.I):
            if ddmm(m.group(2)) >= ref:
                lib.append((ddmm(m.group(2)), '%s %s' % (x['pf'], m.group(2))))
                break
    if not lib:
        lib = [(ddmm(x['previsao']), '%s %s' % (x['pf'], x['previsao'])) for x in linhas if x['previsao'] and ddmm(x['previsao']) >= ref]
    lib.sort()
    infos.append(['LIBERAÇÕES PREVISTAS', 'green', ' · '.join(t for _, t in lib[:5]) or 'Nenhuma informada'])
    sem = [x['pf'] for x in linhas if not x['previsao']]
    infos.append(['SEM PREVISÃO CADASTRADA', 'gray', (' · '.join(sem) + ' · cadastrar no sistema') if sem else 'Todas com previsão'])
    return infos


def fontes_css():
    faces = []
    for fam, pref, ws in [('Barlow Condensed', 'barlow-condensed', [500, 600, 700]), ('IBM Plex Sans', 'ibm-plex-sans', [400, 500, 600, 700])]:
        for w in ws:
            b = base64.b64encode((AQUI / 'fontes' / ('%s-latin-%d-normal.woff2' % (pref, w))).read_bytes()).decode()
            faces.append("@font-face{font-family:'%s';font-weight:%d;font-style:normal;font-display:block;src:url(data:font/woff2;base64,%s) format('woff2')}" % (fam, w, b))
    return ''.join(faces)


def cifrar(dados, senha):
    pt = json.dumps(dados, ensure_ascii=False).encode()
    salt, iv, it = os.urandom(16), os.urandom(12), 250000
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=it).derive(senha.encode())
    ct = AESGCM(key).encrypt(iv, pt, None)
    b = lambda x: base64.b64encode(x).decode()
    return json.dumps({'salt': b(salt), 'iv': b(iv), 'iter': it, 'ct': b(ct)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--maqpar', required=True)
    ap.add_argument('--preventiva', required=True)
    ap.add_argument('--horimetro', help='PDF com a camada ULTIMO HORIMETRO (opcional)')
    ap.add_argument('--config', required=True)
    ap.add_argument('--saida', required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding='utf-8'))

    mq = extrai_maqpar.ler(a.maqpar)
    ref = ddmm(mq['dataRelatorio'])
    prev = extrai_prev.ler(a.preventiva)
    prev['terceiros'] = cfg.get('terceiros', '8/8 OK')
    if a.horimetro:
        for n, h in extrai_prev.ler_horimetros(a.horimetro).items():
            for sem in prev['semanas']:
                if sem['n'] == n:
                    if len(h['valores']) == len(sem['itens']):
                        for it, v in zip(sem['itens'], h['valores']):
                            it.append(v)
                        sem['horimetroData'] = h['data']
                        print('horimetro semana', n, ':', sum(v is not None for v in h['valores']), 'leituras de', h['data'])
                    else:
                        print('AVISO horimetro semana', n, ': linhas nao batem', len(h['valores']), 'x', len(sem['itens']))

    agora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
    dados = {
        'atualizado': agora.strftime('%d/%m/%Y %H:%M'),
        'obra': cfg.get('obra', 'OBRA 421 – LUCAS/MT'),
        'frota': int(cfg['frota']),
        'paradas': {
            'dataRelatorio': mq['dataRelatorio'],
            'fonte': '%s (sistema) · planilha: %s · frota base: %d equipamentos próprios' % (
                os.path.basename(a.maqpar), os.path.basename(a.preventiva), int(cfg['frota'])),
            'linhas': [[x['pf'], x['modelo'], x['os'], x['entrada'], x['hora'], x['previsao'], x['dias'],
                        x['obsData'], x['obs'], x['peca'], x.get('prognostico', '')] for x in mq['linhas']],
            'infos': infos_paradas(mq['linhas'], ref),
        },
        'preventivaMes': prev,
    }
    html = (AQUI / 'painel_modelo.html').read_text(encoding='utf-8')
    html = html.replace('/*FONTS*/', fontes_css()).replace('/*DADOS_ENC*/null', cifrar(dados, cfg['senha']))
    pathlib.Path(a.saida).write_text(html, encoding='utf-8')
    print('OK', a.saida, len(html), 'bytes ·', len(mq['linhas']), 'paradas ·',
          sum(len(s['itens']) for s in prev['semanas']), 'preventivas em', len(prev['semanas']), 'semanas')


if __name__ == '__main__':
    main()
