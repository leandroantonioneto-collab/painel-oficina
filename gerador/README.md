# Gerador do painel da oficina (obra 421)

Monta o `index.html` publicado no GitHub Pages a partir de três arquivos que ficam na pasta
`Indicadores Gestao Visual` do computador do Leandro:

| Arquivo | Pasta | Usado para |
|---|---|---|
| `MAQPAR dd.mm.aaaa.pdf` (o mais recente) | `Máquinas paradas/` | Tela 1 · Máquinas paradas |
| `PROJ. PREVENTIVA ... .pdf` (o mais recente) | `Preventiva/` | Telas 2 e 3 · Preventiva da semana e da próxima |
| `Controle_Frota_421.xlsx` (opcional, aba Desmobilização) | `Controle de Frota/` | Tela 4 · Desmobilização · próximos 15 dias |
| `config.json` (senha, frota base) | `TV painel gestao a vista/` | Não vai para o GitHub |

```
pip install pdfplumber cryptography
python3 gerar.py --maqpar MAQPAR.pdf --preventiva PREVENTIVA.pdf --config config.json --desmob Controle_Frota_421.xlsx --saida ../index.html
# opcional: --proxima PROGRAMACAO_MES_SEGUINTE.pdf  (tela "Próxima semana" na última semana do mês)
```

`--desmob` usa `openpyxl` (`pip install openpyxl`). Mostra os equipamentos com status "Programado" e data prevista entre hoje e 15 dias.

Os dados vão criptografados dentro do `index.html` (AES-GCM, chave derivada da senha); sem a senha a página só mostra a tela de bloqueio.
O painel escolhe sozinho a semana atual e a próxima pela data do dia.
