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

try:
    import openpyxl
except ImportError:  # só necessário com --desmob
    openpyxl = None

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


def desmob_do_xlsx(caminho, hoje=None, dias=15):
    """Equipamentos com status Programado e data prevista entre hoje e hoje+dias (aba Desmobilização)."""
    if openpyxl is None:
        raise SystemExit('instale openpyxl: pip install openpyxl')
    tz = datetime.timezone(datetime.timedelta(hours=-3))
    hoje = hoje or datetime.datetime.now(tz).date()
    fim = hoje + datetime.timedelta(days=dias)
    wb = openpyxl.load_workbook(caminho, data_only=True)
    grupos = {}  # prefixo -> grupo (aba Geral, ex.: 'CBM - CAMINHAO BASCULANTE MINERIO')
    wg = wb['Geral']
    cab_g = [c.value for c in wg[1]]
    for r in wg.iter_rows(min_row=2, values_only=True):
        if r[0] and dict(zip(cab_g, r)).get('Grupo'):
            grupos[str(r[0]).strip()] = str(dict(zip(cab_g, r))['Grupo']).strip()
    modelos = {}  # prefixo -> marca / modelo (abas Alugados e Próprios)
    for aba in ('Alugados', 'Próprios'):
        w = wb[aba]
        cab = [c.value for c in w[1]]
        for r in w.iter_rows(min_row=2, values_only=True):
            if r[0]:
                mm = dict(zip(cab, r)).get('Marca / modelo')
                if mm and not str(mm).strip().lower().startswith(('não consta', 'nao consta')):
                    modelos[str(r[0]).strip()] = str(mm).strip()
    sel = []
    for r in list(wb['Desmobilização'].iter_rows(values_only=True))[1:]:
        tipo, pref, fam, st, prev, _, obs = (list(r) + [None] * 7)[:7]
        if st != 'Programado' or not prev:
            continue
        p = str(prev).strip().split('/')
        d = datetime.date(int(p[2]), int(p[1]), int(p[0]))
        if hoje <= d <= fim:
            chave = str(pref).strip()
            sel.append((d, pref, grupos.get(chave) or fam or '', tipo or '', obs or '', modelos.get(chave, '')))
    sel.sort(key=lambda x: (x[0], x[1]))
    return {
        'janela': hoje.strftime('%d/%m/%Y') + ' a ' + fim.strftime('%d/%m/%Y'),
        'fonte': os.path.basename(caminho) + ' · aba Desmobilização · status Programado · gerado em ' + datetime.datetime.now(tz).strftime('%d/%m/%Y %H:%M'),
        'linhas': [[pf, fa, ti, d.strftime('%d/%m/%Y'), ob, md] for d, pf, fa, ti, ob, md in sel],
    }


def ler_abastecimento(caminho):
    """Último registro (data/hora) com leitura de cada equipamento: {prefixo: {'Hora': x, 'KM': y}}."""
    import csv
    ult, maxd = {}, None
    with open(caminho, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            pf = (r.get('Equipe') or '').strip()
            if not pf:
                continue
            try:
                quando = datetime.datetime.strptime(r['dataabastecimento'] + ' ' + (r.get('hora') or '00:00:00'), '%d/%m/%Y %H:%M:%S')
            except ValueError:
                continue
            maxd = max(maxd, quando) if maxd else quando
            for campo in ('Hora', 'KM'):
                try:
                    v = float(str(r.get(campo) or '').replace('.', '').replace(',', '.'))
                except ValueError:
                    continue
                if v > 0 and (campo not in ult.setdefault(pf, {}) or quando >= ult[pf][campo][0]):
                    ult[pf][campo] = (quando, v)
    return ult, (maxd.strftime('%d/%m') if maxd else '')


def escolhe_leitura(leituras, previsto):
    """Escolhe horímetro ou km conforme a escala do horímetro previsto da preventiva."""
    import math
    if not leituras:
        return None
    try:
        alvo = float(str(previsto).replace('.', '').replace(',', '.'))
    except ValueError:
        alvo = 0
    vals = [v for _, v in leituras.values()]
    if alvo <= 0:
        return leituras.get('Hora', (0, vals[0]))[1]
    v = min(vals, key=lambda x: abs(math.log(x / alvo)))
    return int(v) if v == int(v) else v


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
    ap.add_argument('--proxima', help='PDF da programação do mês seguinte (opcional; usado na tela Próxima semana quando a semana atual é a última do mês)')
    ap.add_argument('--abastecimento', help='CSV de abastecimento (Gestão Visual); preenche o último horímetro/km de cada equipamento')
    ap.add_argument('--horimetro', help='PDF com a camada ULTIMO HORIMETRO (opcional)')
    ap.add_argument('--config', required=True)
    ap.add_argument('--saida', required=True)
    ap.add_argument('--desmob', help='planilha Controle_Frota_421.xlsx (aba Desmobilização, opcional)')
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding='utf-8'))

    mq = extrai_maqpar.ler(a.maqpar)
    ref = ddmm(mq['dataRelatorio'])
    prev = extrai_prev.ler(a.preventiva)
    prev['terceiros'] = cfg.get('terceiros', '8/8 OK')
    # formato novo: coluna 'ULTIMO ABASTECIMENTO' já vem na própria planilha (it[10])
    md = re.search(r'(\d\d)[-.](\d\d)', os.path.basename(a.preventiva))
    data_ab = '%s/%s' % md.groups() if md else datetime.datetime.fromtimestamp(os.path.getmtime(a.preventiva)).strftime('%d/%m')
    for sem in prev['semanas']:
        if sem.pop('abast', False):
            sem['horimetroData'] = data_ab
            print('abastecimento semana', sem['n'], ':', sum(it[10] is not None for it in sem['itens']), 'leituras (planilha de', data_ab + ')')
    if a.proxima:
        seg = extrai_prev.ler(a.proxima)['semanas']
        prev['seguinte'] = [w for w in seg if w['itens']]
        print('mês seguinte:', len(prev['seguinte']), 'semanas ·', sum(len(w['itens']) for w in prev['seguinte']), 'preventivas (' + os.path.basename(a.proxima) + ')')

    if a.abastecimento:
        ult, data_csv = ler_abastecimento(a.abastecimento)
        for sem in prev['semanas'] + prev.get('seguinte', []):
            n = 0
            for it in sem['itens']:
                v = escolhe_leitura(ult.get(it[0]), it[2])
                while len(it) < 11:
                    it.append(None)
                it[10] = v
                n += v is not None
            sem['horimetroData'] = data_csv
            print('abastecimento semana', sem['titulo'], ':', n, 'de', len(sem['itens']), 'leituras (CSV até', data_csv + ')')
    if a.horimetro and not a.abastecimento:
        for n, h in extrai_prev.ler_horimetros(a.horimetro).items():
            for sem in prev['semanas']:
                if sem['n'] == n and 'horimetroData' not in sem:
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
    if a.desmob:
        dados['desmob'] = desmob_do_xlsx(a.desmob)
        print('desmobilização:', len(dados['desmob']['linhas']), 'equipamentos na janela')
    html = (AQUI / 'painel_modelo.html').read_text(encoding='utf-8')
    html = html.replace('/*FONTS*/', fontes_css()).replace('/*DADOS_ENC*/null', cifrar(dados, cfg['senha']))
    pathlib.Path(a.saida).write_text(html, encoding='utf-8')
    print('OK', a.saida, len(html), 'bytes ·', len(mq['linhas']), 'paradas ·',
          sum(len(s['itens']) for s in prev['semanas']), 'preventivas em', len(prev['semanas']), 'semanas')


if __name__ == '__main__':
    main()
